import re
from typing import ClassVar

from saltbox_core.salt.exceptions import StopProcessing
from saltbox_core.salt.handlers.base_handler import BaseMessageHandler, MessageDataType


class PresenceMessageHandler(BaseMessageHandler):
    """
    A message handler for salt presence messages
    """

    tag_patterns: ClassVar[list[re.Pattern[str]]] = [re.compile(r'^salt/presence/present$')]

    def extract_minion_ids(self, match: re.Match, master_id: str, data: MessageDataType) -> list[str]:
        minion_ids: list[str] = data['present']
        return minion_ids

    def is_should_create_minions(self, data: MessageDataType) -> bool:
        return True

    async def process(self, match: re.Match, master_id: str, data: MessageDataType) -> None:
        await self.minion_service.process_presence(master_id=master_id, minions=data['present'])

        raise StopProcessing()
