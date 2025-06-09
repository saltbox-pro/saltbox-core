from typing import Any

from faststream.redis import RedisBroker, RedisMessage

from salt_box_core.db.mongo.config import get_mongo_db
from salt_box_core.event_bus.master_bus_base_messages import BusMasterMessage
from salt_box_core.event_bus.master_bus_middlewares import MastersAuthMiddleware
from salt_box_core.masters.repositories.master_repository import MasterRepository
from salt_box_core.masters.services.master_service import MasterService
from salt_box_core.settings.repository import SettingsSlsRepoRepository
from salt_box_core.settings.schemas.event_bus_schemas import ListSlsReposMessage, MasterMessageSlsRepoModel


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


# TODO (a.karmanov): Make generic send_message_to_every_master()
async def notify_masters() -> None:
    mongo_db = get_mongo_db()
    master_repo = MasterRepository(mongo_db)
    sls_repo_repo = SettingsSlsRepoRepository(mongo_db)
    masters = await MasterService(master_repo).get_list(query={}, skip=0, limit=0)
    active_repos = await sls_repo_repo.get_list(query={'is_active': True}, skip=0, limit=0)
    msg_repos = [MasterMessageSlsRepoModel(**repo.dict()) for repo in active_repos]
    for m_obj in masters:
        msg = ListSlsReposMessage(repos=msg_repos, master=m_obj.master_id)
        await send_message_to_master(msg, 'sync_repos')
