from typing import Any

from faststream.redis import RedisBroker, RedisMessage
from saltbox_bridge_messages import CoreEmptyMessage, CoreMessageBase, MasterStatus

from salt_box_core.db.mongo.config import get_mongo_db
from salt_box_core.event_bus.master_bus_middlewares import MastersAuthMiddleware
from salt_box_core.masters.repositories.master_repository import MasterRepository
from salt_box_core.masters.schemas.master_schemas import MasterModel
from salt_box_core.masters.services.master_service import MasterService


async def send_message_to_master(
    message: CoreMessageBase, message_tag: str, broker: RedisBroker | None = None
) -> None:
    from salt_box_core.event_bus.faststream_redis import get_faststream_broker

    if not broker:
        broker = get_faststream_broker(middlewares=[MastersAuthMiddleware])

    async with broker as br:
        await br.publish(message=message, channel=f'master_{message_tag}')


async def send_message_and_wait_response_to_master(
    message: CoreMessageBase, message_tag: str, response_timeout: float = 3.0, broker: RedisBroker | None = None
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
    message_type: type[CoreMessageBase],
    query: dict[str, Any] | None = None,
    **message_kwargs: Any,
) -> None:
    """
    Send message of `message_type` with `message_kwargs` for all masters by `query`

    By default `query` matches accepted only masters.
    """
    if query is None:
        query = {'status': MasterStatus.ACCEPTED.value}
    message_kwargs.pop('master', None)
    mongo_db = get_mongo_db()
    master_repo = MasterRepository(mongo_db)
    masters = await MasterService(master_repo).get_list(query=query, skip=0, limit=0)
    for m_obj in masters:
        msg = message_type(master=m_obj.master_id, **message_kwargs)
        await send_message_to_master(msg, 'sync_saltbox')


async def notify_master_on_repos_update(master: MasterModel) -> None:
    msg = CoreEmptyMessage(master=master.master_id)
    await send_message_to_master(message=msg, message_tag='sync_saltbox')


async def notify_accepted_masters_on_repos_update() -> None:
    await send_message_to_every_master('sync_saltbox', CoreEmptyMessage)
