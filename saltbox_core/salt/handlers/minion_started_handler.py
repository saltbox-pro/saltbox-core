import re
from typing import ClassVar

from saltbox_core.config import SETTINGS
from saltbox_core.jobs.schemas.job_schemas import AUTO_GRAINS_REQUEST_SOURCE, AUTO_PILLAR_REFRESH_SOURCE
from saltbox_core.salt.exceptions import StopProcessing
from saltbox_core.salt.handlers.base_handler import BaseMessageHandler, MessageDataType


class MinionStartedMessageHandler(BaseMessageHandler):
    """
    A message handler for salt minion started messages
    """

    tag_patterns: ClassVar[list[re.Pattern[str]]] = [re.compile(r'^salt/minion/(?P<mid>.+)/start$')]

    async def process(self, match: re.Match, master_id: str, data: MessageDataType) -> None:
        mid = match.group('mid')

        await self._create_auto_job(
            master_id=master_id,
            fun='grains.items',
            tgt=mid,
            tgt_type='glob',
            source=AUTO_GRAINS_REQUEST_SOURCE,
            ttl=SETTINGS.auto_grains_request_ttl,
        )
        await self._create_auto_job(
            master_id=master_id,
            fun='saltutil.refresh_pillar',
            tgt=mid,
            tgt_type='glob',
            source=AUTO_PILLAR_REFRESH_SOURCE,
            ttl=SETTINGS.auto_pillar_refresh_ttl,
            kwarg={'wait': True},
        )

        raise StopProcessing()
