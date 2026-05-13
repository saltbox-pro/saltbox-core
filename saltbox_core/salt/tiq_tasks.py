from typing import Annotated, Any

from taskiq import TaskiqDepends

from saltbox_core.config import SETTINGS
from saltbox_core.salt.events_handler import salt_events_handler
from saltbox_core.salt.schemas.salt_keys import SaltKeyMinion
from saltbox_core.salt.services.salt_key import SaltKeysService, get_salt_key_service
from saltbox_core.tkq import broker


@broker.task(
    retry_on_error=True,
    max_retries=SETTINGS.salt_taskiq_task_retries_count,
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


@broker.task(
    retry_on_error=True,
    max_retries=10,
    use_jitter=True,
    use_delay_exponent=True,
    max_delay_exponent=30,
)
async def delete_minion_salt_keys_task(
    minion_id: str,
    master_id: str,
    salt_key_service: Annotated[SaltKeysService, TaskiqDepends(get_salt_key_service)],
) -> None:
    await salt_key_service.delete_keys(minions=[SaltKeyMinion(minion_id=minion_id, salt_master=master_id)])
