import re
import sys
from typing import ClassVar

from saltbox_core.salt.handlers.base_handler import BaseMessageHandler, MessageDataType


class SaltMessageMetricMessageHandler(BaseMessageHandler):
    """
    A message handler for salt payload size
    """

    METRIC_TAG = 'metrics:salt_message'
    AVAILABLE_TAG_NAME_TO_REGEX: ClassVar[dict[str, re.Pattern]] = {
        'job_ret': re.compile(r'salt/job/(?P<jid>\d{20})/ret/(?P<mid>.+)'),
        'job_new': re.compile(r'^salt/job/(?P<jid>\d{20})/new$'),
        'minion/refresh': re.compile(r'^minion/refresh/[a-z-]+-[a-f0-9]{12}$'),
    }
    tag_patterns: ClassVar[list[re.Pattern[str]]] = list(AVAILABLE_TAG_NAME_TO_REGEX.values())

    async def process(self, match: re.Match, master_id: str, data: MessageDataType) -> None: ...

    async def _prepare_metrics_data(self, match: re.Match, master_id: str, tag: str, data: MessageDataType) -> dict:
        metrics_data = await super()._prepare_metrics_data(match=match, master_id=master_id, tag=tag, data=data)
        tag_name = None

        for _tag_name, tag_pattern in self.AVAILABLE_TAG_NAME_TO_REGEX.items():
            if re.match(tag_pattern, tag):
                tag_name = _tag_name
                break

        if tag_name:
            metrics_data['tag_name'] = tag_name

        metrics_data.update(
            {
                'payload_size': sys.getsizeof(data),
                'tag': tag,
            }
        )

        return metrics_data
