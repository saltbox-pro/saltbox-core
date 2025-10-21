import re
from datetime import datetime
from typing import ClassVar

import redis.asyncio as aioredis

from saltbox_core.minion_collections.services.minion_service import MinionService
from saltbox_core.salt.exceptions import StopProcessing
from saltbox_core.salt.handlers.base_handler import BaseMessageHandler, MessageDataType


class PresenceMessageHandler(BaseMessageHandler):
    """
    A message handler for salt presence messages
    """

    tag_patterns: ClassVar[list[re.Pattern[str]]] = [re.compile(r'^salt/presence/present$')]

    def __init__(self, redis_client: aioredis.Redis, minion_service: MinionService) -> None:
        super().__init__(redis_client)

        self.minion_service = minion_service

    async def process(self, match: re.Match, master_id: str, data: MessageDataType) -> None:
        await self.minion_service.process_presence(
            master_id=master_id,
            minions=data['present'],
            stamp=datetime.fromisoformat(data['_stamp']).timestamp(),
        )

        raise StopProcessing()
