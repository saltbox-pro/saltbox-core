import abc
import asyncio
import json
import re

import redis.asyncio as aioredis

from saltbox_core.config import logger
from saltbox_core.jobs.schemas.job_schemas import JobModel
from saltbox_core.jobs.services.job_return_service import JobReturnService
from saltbox_core.jobs.services.job_services import JobService
from saltbox_core.salt.handlers.base_handler import BaseMessageHandler, MessageDataType


class BaseJobMessageHandler(BaseMessageHandler, abc.ABC):
    """
    A base message handler for new job salt message when
    """

    METRIC_TAG: str
    METRIC_TASK_TAG: str

    def __init__(
        self,
        redis_client: aioredis.Redis,
        job_service: JobService,
        job_return_service: JobReturnService,
    ) -> None:
        super().__init__(redis_client)

        self.job_service = job_service
        self.job_return_service = job_return_service

    async def _handle(self, match: re.Match, master_id: str, tag: str, data: MessageDataType) -> None:
        normalized_data = await self.normalize_data(match=match, master_id=master_id, tag=tag, data=data)
        jid = match.group('jid')
        job = await self.get_job(jid=jid, master_id=master_id, data=normalized_data)

        tid: str | None = None
        if job and job.source and job.source.type == 'task':
            tid = job.source.id

        process_metrics_task = None
        if self.can_process_metrics():
            process_metrics_task = asyncio.create_task(
                self.process_metrics(match=match, master_id=master_id, tag=tag, data={**normalized_data}, tid=tid)
            )
        await self.process(match=match, master_id=master_id, data=normalized_data, job=job, tid=tid)
        if process_metrics_task is not None:
            await process_metrics_task

    @abc.abstractmethod
    async def get_job(self, jid: str, master_id: str, data: MessageDataType) -> JobModel: ...

    @abc.abstractmethod
    async def process(
        self,
        match: re.Match,
        master_id: str,
        data: MessageDataType,
        job: JobModel | None = None,
        tid: str | None = None,
    ) -> None: ...

    async def _prepare_metrics_data(
        self, match: re.Match, master_id: str, tag: str, data: MessageDataType, tid: str | None = None
    ) -> dict:
        return await super()._prepare_metrics_data(match=match, master_id=master_id, tag=tag, data=data)

    async def process_metrics(
        self, match: re.Match, master_id: str, tag: str, data: MessageDataType, tid: str | None = None
    ) -> None:
        await super().process_metrics(match=match, master_id=master_id, tag=tag, data=data)

        if tid:
            await self.redis_client.publish(
                channel=self.METRIC_TASK_TAG,
                message=json.dumps(
                    await self._prepare_metrics_data(match=match, master_id=master_id, tag=tag, data=data, tid=tid)
                ),
            )
