import abc
import asyncio
import json
import re
from typing import Any

from redis import asyncio as aioredis

from saltbox_bridge_messages import SaltTgtType
from saltbox_core.config import SETTINGS, logger
from saltbox_core.jobs.exceptions import JobCreateException
from saltbox_core.jobs.schemas.job_schemas import AUTO_GRAINS_REQUEST_SOURCE, JobCreateSchema
from saltbox_core.jobs.services.job_services import JobService
from saltbox_core.minion_collections.services.minion import MinionService
from saltbox_sdk.db.schemas_base import SYSTEM_SHORT_USER, Source

MessageDataType = dict[str, Any]


class BaseMessageHandler(abc.ABC):
    """
    A base class for handling salt.box messages
    """

    def __init__(self, redis_client: aioredis.Redis, minion_service: MinionService, job_service: JobService) -> None:
        self.redis_client = redis_client
        self.minion_service = minion_service
        self.job_service = job_service

    METRIC_TAG: str | None = None

    @property
    @abc.abstractmethod
    def tag_patterns(self) -> list[re.Pattern[str]]: ...

    async def normalize_data(self, match: re.Match, master_id: str, tag: str, data: MessageDataType) -> MessageDataType:
        return {**data}

    async def handle(self, master_id: str, tag: str, data: MessageDataType) -> None:
        """
        If tag matches tag_patterns, process message

        Args:
            master_id: salt master id
            tag: salt message tag
            data: salt message data

        Raises:
            StopProcessing: when no need to process the message with other handlers
        """
        for tag_pattern in self.tag_patterns:
            if match := tag_pattern.match(tag):
                await self._create_missing_minions(match=match, master_id=master_id, data=data)
                await self._handle(match=match, master_id=master_id, tag=tag, data=data)
                return

    def extract_minion_ids(self, match: re.Match, master_id: str, data: MessageDataType) -> list[str]:
        return []

    def is_should_create_minions(self, data: MessageDataType) -> bool:
        return False

    def is_should_request_grains(self, data: MessageDataType) -> bool:
        return True

    async def _create_missing_minions(self, match: re.Match, master_id: str, data: MessageDataType) -> None:
        if not self.is_should_create_minions(data):
            return

        minion_ids = self.extract_minion_ids(match=match, master_id=master_id, data=data)
        if not minion_ids:
            return

        created_ids, existing_ids_needing_grains = await self.minion_service.create_missing(
            master_id=master_id, minion_ids=minion_ids
        )

        if not self.is_should_request_grains(data):
            return

        minion_ids_needing_grains = created_ids + existing_ids_needing_grains
        if not minion_ids_needing_grains:
            return

        requested_ids = await self.job_service.get_minion_ids_with_active_jobs(
            master_id=master_id, minion_ids=minion_ids_needing_grains, source=AUTO_GRAINS_REQUEST_SOURCE
        )

        minion_ids_to_request = []
        for minion_id in minion_ids_needing_grains:
            if minion_id not in requested_ids:
                minion_ids_to_request.append(minion_id)

        if minion_ids_to_request:
            await self._create_auto_job(
                master_id=master_id,
                fun='grains.items',
                tgt=minion_ids_to_request,
                tgt_type='list',
                source=AUTO_GRAINS_REQUEST_SOURCE,
                ttl=SETTINGS.auto_grains_request_ttl,
            )

    async def _create_auto_job(
        self,
        master_id: str,
        fun: str,
        tgt: str | list[str],
        tgt_type: SaltTgtType,
        source: Source,
        ttl: int,
        kwarg: dict[str, Any] | None = None,
    ) -> None:
        try:
            await self.job_service.create(
                data=JobCreateSchema.model_validate(
                    {
                        'tgt': tgt,
                        'tgt_type': tgt_type,
                        'salt_master': master_id,
                        'fun': fun,
                        'kwarg': kwarg,
                        'user': SYSTEM_SHORT_USER,
                        'source': source,
                        'ttl': ttl,
                    }
                ),
            )
        except JobCreateException as e:
            logger.warning('Failed to create %s job for minions %s on master "%s": %s', fun, tgt, master_id, e)

    async def _handle(self, match: re.Match, master_id: str, tag: str, data: MessageDataType) -> None:
        data = await self.normalize_data(match=match, master_id=master_id, tag=tag, data=data)

        process_metrics_task = None
        if self.can_process_metrics():
            process_metrics_task = asyncio.create_task(
                self.process_metrics(match=match, master_id=master_id, tag=tag, data=data)
            )

        await self.process(match=match, master_id=master_id, data=data)

        if process_metrics_task is not None:
            await process_metrics_task

    def can_process_metrics(self) -> bool:
        if SETTINGS.is_module_metric_on and self.METRIC_TAG:
            return True

        return False

    async def _prepare_metrics_data(self, match: re.Match, master_id: str, tag: str, data: MessageDataType) -> dict:
        """
        Prepare metrics data

        Args:
            match: matched salt message tag
            master_id: salt master id
            tag: salt message tag
            data: salt message data
        """

        return {
            'master_id': master_id,
        }

    async def process_metrics(self, match: re.Match, master_id: str, tag: str, data: MessageDataType) -> None:
        """
        Process metrics

        Args:
            match: matched salt message tag
            master_id: salt master id
            tag: salt message tag
            data: salt message data
        """

        if not self.METRIC_TAG:
            return

        await self.redis_client.publish(
            channel=self.METRIC_TAG, message=json.dumps(await self._prepare_metrics_data(match, master_id, tag, data))
        )

    @abc.abstractmethod
    async def process(self, match: re.Match, master_id: str, data: MessageDataType) -> None:
        """
        Take action on message

        Args:
            match: matched salt message tag
            master_id: salt master id
            data: salt message data

        Raises:
            StopProcessing: when no need to process the message with other handlers
        """
