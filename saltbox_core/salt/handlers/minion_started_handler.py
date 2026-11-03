import re
from typing import ClassVar

from saltbox_core.salt.exceptions import StopProcessing
from saltbox_core.salt.handlers.base_handler import BaseMessageHandler, MessageDataType


class MinionStartedMessageHandler(BaseMessageHandler):
    """
    A message handler for salt minion started messages
    """

    tag_patterns: ClassVar[list[re.Pattern[str]]] = [re.compile(r'^salt/minion/(?P<mid>.+)/start$')]

    async def process(self, match: re.Match, master_id: str, data: MessageDataType) -> None:
        await self._request_grains(master_id=master_id, tgt=match.group('mid'), tgt_type='glob')

        raise StopProcessing()
