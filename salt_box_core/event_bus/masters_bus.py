from typing import Any

from faststream.redis import RedisBroker, RedisMessage
from saltbox_bridge_messages import BusMasterMessage, EmptyMessage

from salt_box_core.db.mongo.config import get_mongo_db
from salt_box_core.event_bus.master_bus_middlewares import MastersAuthMiddleware
from salt_box_core.masters.repositories.master_repository import MasterRepository
from salt_box_core.masters.services.master_service import MasterService
from salt_box_core.settings.repository import SettingsSlsRepoRepository


async def send_message_to_master(
    message: BusMasterMessage, message_tag: str, broker: RedisBroker | None = None
) -> None:
    from salt_box_core.event_bus.faststream_redis import get_faststream_broker

    if not broker:
        broker = get_faststream_broker(middlewares=[MastersAuthMiddleware])

    async with broker as br:
        await br.publish(message=message, channel=f'master_{message_tag}')


async def send_message_and_wait_response_to_master(
    message: BusMasterMessage, message_tag: str, response_timeout: float = 3.0, broker: RedisBroker | None = None
) -> Any:
    from salt_box_core.event_bus.faststream_redis import get_faststream_broker

    if not broker:
        broker = get_faststream_broker(middlewares=[MastersAuthMiddleware])

    async with broker as br:
        response: RedisMessage = await br.request(  # type: ignore
            message,
            channel=f'master_{message_tag}',
            timeout=response_timeout,
        )
        return await response.decode()


async def send_message_to_every_master(
        message_tag: str,
        message_type: type[BusMasterMessage],
        **message_kwargs: dict[str, Any]) -> None:
    mongo_db = get_mongo_db()
    master_repo = MasterRepository(mongo_db)
    masters = await MasterService(master_repo).get_list(query={}, skip=0, limit=0)
    for m_obj in masters:
        msg = message_type(master=m_obj.master_id, **message_kwargs)
        await send_message_to_master(msg, 'sync_repos')


async def notify_masters_on_repos_update() -> None:
    return await send_message_to_every_master('sync_repos', EmptyMessage)
