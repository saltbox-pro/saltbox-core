from __future__ import annotations

import re
from typing import Any, ClassVar

import pymongo
from beanie import Document

from fastms_core.minions.models import Minion, MinionCollection
from fastms_core.salt.http_client import SALT_CLIENT, SaltHttpClientError
from fastms_core.tasks.schemas import (
    TaskJob,
    TaskJobStatus,
    TaskJobTarget,
    TaskSchema,
    TaskTemplateSchema,
    TaskTemplateVariable,
    TaskTgtType,
)


class Task(Document, TaskSchema):
    def __can_start_job(self) -> bool:
        return True

    async def __fill_jobs_queue(self) -> None:
        if self.targets_queue is None:
            self.targets_queue = []

        minions: list[Minion] = []

        if self.tgt_type == TaskTgtType.minions_list:
            minions_ids = ','.split(self.tgt_value)
            minions = await Minion.find({'_id': {'$in': minions_ids}}).to_list()
        elif self.tgt_type == TaskTgtType.minions_collection:
            collection: MinionCollection | None = await MinionCollection.get(self.tgt_value)

            if collection:
                minions = await Minion.find(collection.query).to_list()
            else:
                msg = f'Minion collection with id {self.tgt_type} not found'
                raise ValueError(msg)

        targets_lists: list[list[str]] = []
        temp_targets_list: list[str] = []

        while len(minions) > 0:
            temp_targets_list.append(minions.pop(0).minion_id)

            if self.batch_size and len(temp_targets_list) >= (self.batch_size - 1):
                targets_lists.append(temp_targets_list[:])
                temp_targets_list = []
        else:
            if len(temp_targets_list):
                targets_lists.append(temp_targets_list[:])

        for tgt_list in targets_lists:
            self.targets_queue.append(TaskJobTarget(tgt=','.join(tgt_list), tgt_type='list'))

        await self.save()

    async def __check_running_jobs(self) -> None:
        for job in self.jobs:
            if job.status != TaskJobStatus.running:
                continue

        await self.save()

    async def __rub_jobs(self) -> None:
        if not self.targets_queue:
            return

        while self.targets_queue:
            job_targeting = self.targets_queue.pop(0)

            if not self.__can_start_job():
                break
            try:
                ret = await SALT_CLIENT.run_job(
                    tgt=job_targeting.tgt, fun=self.fun, arg=self.task_args, kwarg=self.task_kwargs, tgt_type='list'
                )

                self.jobs.append(TaskJob.model_validate({'jid': str(ret['return'][0]['jid']), 'target': job_targeting}))
            except SaltHttpClientError:
                break

    async def process(self) -> None:
        if self.status != self.TaskStatus.running:
            return
        if self.targets_queue is None:
            await self.__fill_jobs_queue()

        await self.__check_running_jobs()
        await self.__rub_jobs()

        if not self.targets_queue:
            self.status = self.TaskStatus.finished

        await self.save()

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
            elif variable.type == TaskTemplateVariable.TaskTemplateType.integer:
                context[variable.name] = int(variable_value)
            elif variable.type == TaskTemplateVariable.TaskTemplateType.float:
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

    def create_task(self, variables_data: dict, tgt_type: TaskTgtType, tgt_value: str) -> Task:
        context: dict = self.get_context(variables_data)

        task_data = {
            'fun': self.fun,
            'task_args': self.get_task_args(variables_data, context),
            'task_kwargs': self.get_task_kwargs(variables_data, context),
            'tgt_type': tgt_type,
            'tgt_value': tgt_value,
            'batch_size': 100,
        }

        return Task.model_validate(task_data)

    class Settings:
        name = 'task_templates'
        indexes: ClassVar[list] = [
            ('id', pymongo.TEXT),
        ]

    class Config:
        extra = 'allow'
