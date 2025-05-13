from datetime import UTC, datetime

from faststream import Context
from faststream.redis import RedisRouter

from salt_box_core.config import logger
from salt_box_core.db.exceptions import ObjectNotFoundError
from salt_box_core.event_bus.maater_bus_base_messages import AuthMessage, BusMasterMessage, MasterStatusMessage
from salt_box_core.event_bus.master_bus_middlewares import MastersAuthMiddleware
from salt_box_core.masters.schemas.master_schemas import MasterCreateSchema, MasterModel
from salt_box_core.masters.services.master_service import MasterService
from salt_box_core.minion_collections.schemas.event_bus_schemas import MinionGrainsMessage, MinionPresenceMessage
from salt_box_core.minion_collections.schemas.minion_schemas import (
    GrainsSchema,
    MinionCreateSchema,
    MinionModel,
    MinionUpdateSchema,
)
from salt_box_core.minion_collections.services.minion_service import MinionService
from salt_box_core.utilities.gpg import SaltBoxCrypt

router_not_auth = RedisRouter(prefix='master_', middlewares=[])
router = RedisRouter(prefix='master_', middlewares=[MastersAuthMiddleware])


@router_not_auth.subscriber('auth', middlewares=[])
async def auth(
    message: AuthMessage,
    master_service: MasterService = Context(),  # noqa: B008
    saltbox_crypt: SaltBoxCrypt = Context(),  # noqa: B008
) -> AuthMessage:
    try:
        master: MasterModel = await master_service.get_by_master_id(message.master)
    except ObjectNotFoundError:
        master = await master_service.create(
            MasterCreateSchema.model_validate({'master_id': message.master, 'title': message.master})
        )

    if not master.pubkey:
        master.pubkey = message.pubkey
        master = await master_service.update(query=master.id, data=master.model_dump())

    return AuthMessage(**{'master': master.master_id, 'pubkey': saltbox_crypt.pubkey})


@router_not_auth.subscriber('status', middlewares=[])
async def status(
    message: BusMasterMessage,
    master_service: MasterService = Context(),  # noqa: B008
) -> MasterStatusMessage:
    try:
        master: MasterModel = await master_service.get_by_master_id(message.master)
    except ObjectNotFoundError:
        master = await master_service.create(
            MasterCreateSchema.model_validate({'master_id': message.master, 'title': message.master})
        )

    return MasterStatusMessage(master=master.master_id, status=master.status, is_pubkey_set=master.is_pubkey_set)


@router.subscriber('grains')
async def grains_handler(
    message: MinionGrainsMessage,
    minion_service: MinionService = Context(),  # noqa: B008
) -> None:
    grains = message.grains
    minion_id = grains['id']

    if grains:
        try:
            minion: MinionModel = await minion_service.get_by_master_and_id(master=message.master, minion_id=minion_id)
            minion.grains = GrainsSchema(**grains)
            await minion_service.update(minion.id, MinionUpdateSchema(**minion.model_dump()))
        except ObjectNotFoundError:
            minion_obj = {
                'minion_id': minion_id,
                'master': message.master,
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
