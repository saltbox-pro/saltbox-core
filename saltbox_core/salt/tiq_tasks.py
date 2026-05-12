from typing import Any

from saltbox_core.config import SETTINGS
from saltbox_core.salt.events_handler import salt_events_handler
from saltbox_core.tkq import broker


@broker.task(
    retry_on_error=True,
    max_retries=SETTINGS.salt_taskiq_task_retries_count,
    delay=0.5,
    use_jitter=True,
    use_delay_exponent=True,
    max_delay_exponent=3,
)
async def process_salt_event_task(
    master_id: str,
    tag: str,
    data: dict[str, Any],
    retries: int,
) -> None:
    await salt_events_handler.process_event(master_id=master_id, tag=tag, data=data, retries=retries)
