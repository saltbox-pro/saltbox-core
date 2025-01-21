from __future__ import annotations

import logging.config
import re
from typing import Any, ClassVar

import pymongo
from beanie import Document

from fastms_core.config import LOG_CONFIG
from fastms_core.tasks.schemas import (
    TaskSchema,
    TaskTemplateSchema,
    TaskTemplateVariable,
    TaskTgtType,
)

logging.config.dictConfig(LOG_CONFIG.model_dump())

logger = logging.getLogger(__name__)


class Task(Document, TaskSchema):
    class Settings:
        name = 'tasks'
        indexes: ClassVar[list] = [
            ('id', pymongo.TEXT),
        ]

    class Config:
        extra = 'allow'


class TaskTemplate(Document, TaskTemplateSchema):
    def get_context(self, variables_data: dict) -> dict:  # noqa: C901
        context: dict = {}

        for variable in self.variables:
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

    def get_task_args(self, variables_data: dict, context: dict[str, Any] | None) -> list:
        if context is None:
            context = self.get_context(variables_data)

        task_args: list = []
        variable_pattern = re.compile(r'^<<task_var\.(.+)>>$')

        for arg in self.task_args:
            from_context_match = re.match(variable_pattern, arg)

            if from_context_match:
                arg_value = context[from_context_match.group(1)]
            else:
                arg_value = arg

            if arg_value is not None:
                task_args.append(arg_value)

        return task_args

    def get_task_kwargs(self, variables_data: dict, context: dict[str, Any] | None) -> dict:
        if context is None:
            context = self.get_context(variables_data)

        task_kwargs: dict = {}
        variable_pattern = re.compile(r'^<<task_var\.(.+)>>$')

        for kwarg_key, kwarg_raw_value in self.task_kwargs.items():
            from_context_match = re.match(variable_pattern, kwarg_raw_value)

            if from_context_match:
                kwarg_value = context[from_context_match.group(1)]
            else:
                kwarg_value = kwarg_raw_value

            if kwarg_value is not None:
                task_kwargs[kwarg_key] = kwarg_value

        return task_kwargs

    async def create_task(
        self,
        variables_data: dict,
        tgt_type: TaskTgtType,
        tgt_value: str,
        batch_size: int | None = None,
        max_retries: int = 3,
    ) -> Task:
        context: dict = self.get_context(variables_data)

        task_data = {
            'task_template_id': self.id,
            'fun': self.fun,
            'task_args': self.get_task_args(variables_data, context),
            'task_kwargs': self.get_task_kwargs(variables_data, context),
            'tgt_type': tgt_type,
            'tgt_value': tgt_value,
            'batch_size': batch_size,
            'max_retries': max_retries,
        }

        task = Task.model_validate(task_data)
        await task.save()

        return task

    class Settings:
        name = 'task_templates'
        indexes: ClassVar[list] = [
            ('id', pymongo.TEXT),
        ]

    class Config:
        extra = 'allow'
