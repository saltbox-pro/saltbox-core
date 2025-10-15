import abc
import asyncio
import json
import re
from typing import Any

from redis import asyncio as aioredis

from saltbox_core.config import SETTINGS

MessageDataType = dict[str, Any]


class BaseMessageHandler(abc.ABC):
    """
    A base class for handling salt.box messages
    """

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self.redis_client = redis_client

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
                await self._handle(match=match, master_id=master_id, tag=tag, data=data)
                return

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
