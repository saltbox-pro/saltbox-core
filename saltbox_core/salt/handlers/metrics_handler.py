import json
import re
import sys
from typing import Any, ClassVar

from saltbox_core.salt.handlers.base_handler import BaseMessageHandler, MessageDataType


class SaltMessageMetricMessageHandler(BaseMessageHandler):
    """
    A message handler for salt payload size
    """

    METRIC_TAG = 'metrics:salt_message'
    AVAILABLE_TAG_PATTERNS_TO_TAG_NAME: ClassVar[dict[re.Pattern, str]] = {
        re.compile(r'salt/job/(?P<jid>\d{20})/ret/(?P<mid>.+)'): 'salt/job/ret',
        re.compile(r'^salt/job/(?P<jid>\d{20})/new$'): 'salt/job/new',
        re.compile(r'salt/run/(?P<jid>\d{20})/ret$'): 'salt/run/ret',
        re.compile(r'^salt/run/(?P<jid>\d{20})/new$'): 'salt/run/new',
        re.compile(r'^minion/refresh/[a-z-]+-[a-f0-9]{12}$'): 'minion/refresh',
        re.compile(r'^salt/minion/(?P<mid>.+)/start$'): 'salt/minion/start',
        re.compile(r'^minion_start$'): 'salt/minion/start',
        re.compile(r'^salt/auth$'): 'salt/auth',
        re.compile(r'^salt/presence/present$'): 'salt/presence',
        re.compile(r'^salt/presence/change$'): 'salt/presence',
    }
    OTHER_TAG_NAME = 'other'
    tag_patterns: ClassVar[list[re.Pattern[str]]] = list(AVAILABLE_TAG_PATTERNS_TO_TAG_NAME.keys())

    async def handle(self, master_id: str, tag: str, data: MessageDataType) -> None:
        tag_name: str | None = None
        for tag_pattern, _tag_name in self.AVAILABLE_TAG_PATTERNS_TO_TAG_NAME.items():
            if tag_pattern.match(tag):
                tag_name = _tag_name
                break

        if self.can_process_metrics():
            metrics_data: dict[str, Any] = {
                'master_id': master_id,
                'payload_size': sys.getsizeof(data),
                'tag': tag,
                'tag_name': tag_name if tag_name else self.OTHER_TAG_NAME,
            }

            await self.redis_client.publish(channel=self.METRIC_TAG, message=json.dumps(metrics_data))

    async def process(self, match: re.Match, master_id: str, data: MessageDataType) -> None: ...
