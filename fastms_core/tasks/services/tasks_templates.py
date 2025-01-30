import re
from typing import Annotated, Any

from fastapi import Depends

from fastms_core.db.redis import RedisDependency
from fastms_core.tasks.repository import TaskTemplateRepository
from fastms_core.tasks.schemas import (
    TaskTemplateCreateSchema,
    TaskTemplateListSchema,
    TaskTemplateSchema,
    TaskTemplateUpdateSchema,
    TaskTemplateVariable,
)
from fastms_core.utilities.service_base import BaseService


class TaskTemplateService(
    BaseService[
        TaskTemplateRepository,
        TaskTemplateSchema,
        TaskTemplateListSchema,
        TaskTemplateCreateSchema,
        TaskTemplateUpdateSchema
    ]
):
    repository_class = TaskTemplateRepository

    def __init__(self, rdb: RedisDependency):
        self.rdb = rdb
        super().__init__()

    def get_context(self, task_template: TaskTemplateSchema, variables_data: dict) -> dict:  # noqa: C901
        context: dict = {}

        for variable in task_template.variables:
            try:
                variable_value = variables_data[variable.name]
            except KeyError:
                variable_value = variable.default_value

            if variable.type == TaskTemplateVariable.TaskTemplateType.string:
                context[variable.name] = str(variable_value)
            elif variable.type == TaskTemplateVariable.TaskTemplateType.number:
                if str(variable_value).isdigit():
                    context[variable.name] = int(variable_value)
                else:
                    context[variable.name] = float(variable_value)
            elif variable.type == TaskTemplateVariable.TaskTemplateType.bool:
                context[variable.name] = bool(variable_value)
            elif variable.type == TaskTemplateVariable.TaskTemplateType.choices:
                if not variable.choices or not len(variable.choices):
                    msg = f'Variable {variable.name} has no choices'
                    raise ValueError(msg)

                if type(variable_value) not in [str, int, float]:
                    msg = f'Variable {variable.name} has invalid type'
                    raise ValueError(msg)

                if variable_value in variable.choices:
                    context[variable.name] = variable_value
                else:
                    msg = f'Value "{variable_value}" is not a valid choice"'
                    raise ValueError(msg)

        return context

    def get_task_args(
            self, task_template: TaskTemplateSchema, variables_data: dict, context: dict[str, Any] | None
    ) -> list:
        if context is None:
            context = self.get_context(task_template=task_template, variables_data=variables_data)

        task_args: list = []
        variable_pattern = re.compile(r'^<<task_var\.(.+)>>$')

        for arg in task_template.task_args:
            from_context_match = re.match(variable_pattern, arg)

            if from_context_match:
                arg_value = context[from_context_match.group(1)]
            else:
                arg_value = arg

            if arg_value is not None:
                task_args.append(arg_value)

        return task_args

    def get_task_kwargs(
            self, task_template: TaskTemplateSchema, variables_data: dict, context: dict[str, Any] | None
    ) -> dict:
        if context is None:
            context = self.get_context(task_template=task_template, variables_data=variables_data)

        task_kwargs: dict = {}
        variable_pattern = re.compile(r'^<<task_var\.(.+)>>$')

        for kwarg_key, kwarg_raw_value in task_template.task_kwargs.items():
            from_context_match = re.match(variable_pattern, kwarg_raw_value)

            if from_context_match:
                kwarg_value = context[from_context_match.group(1)]
            else:
                kwarg_value = kwarg_raw_value

            if kwarg_value is not None:
                task_kwargs[kwarg_key] = kwarg_value

        return task_kwargs


async def get_task_template_service(rdb: RedisDependency):
    task_template_service = TaskTemplateService(rdb=rdb)
    yield task_template_service


TaskTemplateServiceDependency = Annotated[TaskTemplateService, Depends(get_task_template_service)]
