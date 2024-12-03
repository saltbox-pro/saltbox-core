from __future__ import annotations

import json
import logging.config
import re
from typing import Any, ClassVar

import pymongo
from beanie import Document
from redis import asyncio as aioredis

from fastms_core.config import LOG_CONFIG, SETTINGS
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

logging.config.dictConfig(LOG_CONFIG.model_dump())

logger = logging.getLogger(__name__)


class Task(Document, TaskSchema):
    @classmethod
    async def __get_redis(cls) -> aioredis.Redis:
        return await aioredis.from_url(SETTINGS.redis_url, **SETTINGS.redis_connection_kwargs)

    def __can_start_job(self) -> bool:
        for job in self.jobs:
            if job.status == TaskJobStatus.running:
                return False

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

            if self.batch_size and len(temp_targets_list) >= self.batch_size:
                targets_lists.append(temp_targets_list[:])
                temp_targets_list = []
        else:
            if len(temp_targets_list):
                targets_lists.append(temp_targets_list[:])

        for tgt_list in targets_lists:
            self.targets_queue.append(TaskJobTarget(tgt=','.join(tgt_list), tgt_type='list'))

        await self.save()

    async def __check_running_jobs(self, redis: aioredis.Redis) -> None:
        minions_ids_with_failed_job: list[str] = []

        for job in self.jobs:
            if job.status != TaskJobStatus.running:
                continue

            job_returns_data = await redis.hgetall(name=f'job:{job.jid}:return')

            for return_data_s in job_returns_data.values():
                return_data = json.loads(return_data_s)
                minion_id: str = return_data['id']

                self.minions_retries_counts.setdefault(minion_id, 0)
                self.minions_retries_counts[minion_id] += 1

                if return_data['success'] is True:
                    job.status = TaskJobStatus.succeeded
                else:
                    job.status = TaskJobStatus.failed
                    minions_ids_with_failed_job.append(return_data['id'])

        if minions_ids_with_failed_job:
            minions_ids_for_retry: list[str] = []

            for minion_id in minions_ids_with_failed_job:
                if self.minions_retries_counts[minion_id] <= self.max_retries - 1:
                    minions_ids_for_retry.append(minion_id)
                else:
                    self.failed_for_minions.append(minion_id)

            if minions_ids_for_retry:
                if not self.targets_queue:
                    self.targets_queue = []

                self.targets_queue.append(TaskJobTarget(tgt=','.join(minions_ids_for_retry), tgt_type='list'))

        await self.save()

    async def __rub_jobs(self) -> None:
        if not self.targets_queue:
            return

        if self.__can_start_job():
            job_targeting = self.targets_queue.pop(0)

            try:
                ret = await SALT_CLIENT.run_job(
                    tgt=job_targeting.tgt, fun=self.fun, arg=self.task_args, kwarg=self.task_kwargs, tgt_type='list'
                )

                self.jobs.append(TaskJob.model_validate({'jid': str(ret['return'][0]['jid']), 'target': job_targeting}))
            except SaltHttpClientError:
                self.targets_queue.append(job_targeting)

        await self.save()

    async def process(self, redis: aioredis.Redis | None = None) -> None:
        if self.status != self.TaskStatus.running:
            return
        if self.targets_queue is None:
            await self.__fill_jobs_queue()

        if not redis:
            redis = await self.__get_redis()

        await self.__check_running_jobs(redis=redis)
        await self.__rub_jobs()

        if not self.targets_queue:
            for job in self.jobs:
                if job.status == TaskJobStatus.running:
                    break
            else:
                self.status = self.TaskStatus.finished

        await self.save()

    async def run(self) -> None:
        if self.status in [self.TaskStatus.created, self.TaskStatus.stopped]:
            self.status = self.TaskStatus.running
            await self.save()

    async def stop(self) -> None:
        if self.status == self.TaskStatus.running:
            # TODO: stop jobs
            self.status = self.TaskStatus.stopped
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
