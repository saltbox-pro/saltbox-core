from typing import Any

from saltbox_bridge_messages import CoreUpdatePillarCacheRequest
from saltbox_core.event_bus.masters_bus import send_message_and_wait_response_to_master
from saltbox_core.tkq import broker


@broker.task(timeout=30, retry_on_error=True, _retries=3)
async def update_pillar_cache(master_id: str, tgt: str, tgt_type: str) -> Any:
    return await send_message_and_wait_response_to_master(
        message=CoreUpdatePillarCacheRequest(master=master_id, tgt=tgt, tgt_type=tgt_type),
        message_tag='update_pillar_cache',
        response_timeout=30.0,
    )
