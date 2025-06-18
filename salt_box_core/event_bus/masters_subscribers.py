from datetime import UTC, datetime

from faststream import Context
from faststream.redis import RedisRouter
from saltbox_bridge_messages import (
    AuthRequestMessage,
    AuthResponseMessage,
    BusMasterMessage,
    MasterStatusMessage,
)

from salt_box_core.config import logger
from salt_box_core.db.exceptions import ObjectNotFoundError
from salt_box_core.event_bus.master_bus_middlewares import MastersAuthMiddleware
from salt_box_core.masters.schemas.master_schemas import MasterCreateSchema, MasterModel, MasterStatus
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
    message: AuthRequestMessage,
    master_service: MasterService = Context(),  # noqa: B008
    saltbox_crypt: SaltBoxCrypt = Context(),  # noqa: B008
) -> AuthResponseMessage:
    try:
        master: MasterModel = await master_service.get_by_master_id(message.master)
    except ObjectNotFoundError:
        master_dict = {
            'master_id': message.master,
            'title': message.master,
            'gitfs_pubkey': message.gitfs_pubkey,
            'sshfs_pubkey': message.sshfs_pubkey,
        }
        master = await master_service.create(MasterCreateSchema.model_validate(master_dict))

    if not master.pubkey:
        master.pubkey = message.crypt_pubkey
        master = await master_service.update(query=master.id, data=master.model_dump())

    return AuthResponseMessage(crypt_pubkey=saltbox_crypt.pubkey)


@router_not_auth.subscriber('status', middlewares=[])
async def status(
    message: BusMasterMessage,
    master_service: MasterService = Context(),  # noqa: B008
) -> MasterStatusMessage:
    try:
        master: MasterModel = await master_service.get_by_master_id(message.master)
    except ObjectNotFoundError:
        # TODO(a.karmanov): return error or special status (`unknown`)
        return MasterStatusMessage(master=message.master, status=MasterStatus.rejected, is_pubkey_set=False)

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
