from datetime import UTC, datetime

from faststream import Context
from faststream.redis import RedisRouter

from salt_box_core.config import logger
from salt_box_core.db.exceptions import ObjectNotFoundError
from salt_box_core.event_bus.masters_bus import MastersAuthMiddleware
from salt_box_core.minion_collections.schemas.event_bus_schemas import MinionGrainsMessage, MinionPresenceMessage
from salt_box_core.minion_collections.schemas.minion_schemas import (
    GrainsSchema,
    MinionCreateSchema,
    MinionModel,
    MinionUpdateSchema,
)
from salt_box_core.minion_collections.services.minion_service import MinionService

router = RedisRouter(prefix='master_', middlewares=[MastersAuthMiddleware])


@router.subscriber('auth')
def auth() -> None: ...


@router.subscriber('grains')
async def grains_handler(
    message: MinionGrainsMessage,
    minion_service: MinionService = Context(),  # noqa: B008
) -> None:
    grains = message.grains
    minion_id = grains['id']
    master = grains['master']

    if master != message.master:
        return

    if grains:
        try:
            minion: MinionModel = await minion_service.get_by_master_and_id(master=master, minion_id=minion_id)
            minion.grains = GrainsSchema(**grains)
            await minion_service.update(minion.id, MinionUpdateSchema(**minion.model_dump()))
        except ObjectNotFoundError:
            minion_obj = {
                'minion_id': minion_id,
                'master': master,
                'grains': grains,
            }
            await minion_service.create(MinionCreateSchema(**minion_obj))


@router.subscriber('presence')
async def presence_handler(
    message: MinionPresenceMessage,
    minion_service: MinionService = Context(),  # noqa: B008
) -> None:
    last_activity_dt = datetime.fromtimestamp(message.stamp, tz=UTC)

    for minion_id in message.minions:
        try:
            minion: MinionModel = await minion_service.get_by_master_and_id(master=message.master, minion_id=minion_id)
            minion.last_activity = last_activity_dt
            await minion_service.update(minion.id, MinionUpdateSchema(**minion.model_dump()))
        except ObjectNotFoundError:
            logger.info(f'{minion_id} from presence not found in the DB')
