import re
from typing import ClassVar

import redis.asyncio as aioredis

from saltbox_core.jobs.schemas.job_schemas import JobCreateSchema
from saltbox_core.jobs.services.job_services import JobService
from saltbox_core.salt.exceptions import StopProcessing
from saltbox_core.salt.handlers.base_handler import BaseMessageHandler, MessageDataType
from saltbox_sdk.db.schemas_base import SYSTEM_SHORT_USER


class MinionStartedMessageHandler(BaseMessageHandler):
    """
    A message handler for salt minion started messages
    """

    tag_patterns: ClassVar[list[re.Pattern[str]]] = [re.compile(r'^salt/minion/(?P<mid>.+)/start$')]

    def __init__(self, redis_client: aioredis.Redis, job_service: JobService) -> None:
        super().__init__(redis_client)

        self.job_service = job_service

    async def process(self, match: re.Match, master_id: str, data: MessageDataType) -> None:
        mid = match.group('mid')

        await self.job_service.create(
            data=JobCreateSchema.model_validate(
                {
                    'tgt': mid,
                    'tgt_type': 'glob',
                    'salt_master': master_id,
                    'fun': 'grains.items',
                    'user': SYSTEM_SHORT_USER,
                }
            )
        )

        raise StopProcessing()
