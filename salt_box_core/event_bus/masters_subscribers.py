from datetime import UTC, datetime

from faststream import Context
from faststream.redis import RedisRouter
from saltbox_bridge_messages import (
    BridgeAuthRequest,
    BridgeMinionGrainsMessage,
    BridgeMinionPresenceMessage,
    BridgeTestBurstLoadMessage,
    CoreAuthResponse,
    MasterStatus,
)

from salt_box_core.config import logger
from salt_box_core.db.exceptions import ObjectNotFoundError
from salt_box_core.event_bus.master_bus_middlewares import MastersAuthMiddleware
from salt_box_core.masters.schemas.master_schemas import MasterCreateSchema, MasterUpdateSchema, MasterModel
from salt_box_core.masters.services.master_service import MasterService
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
    message: BridgeAuthRequest,
    master_service: MasterService = Context(),  # noqa: B008
    saltbox_crypt: SaltBoxCrypt = Context(),  # noqa: B008
) -> CoreAuthResponse:
    try:
        master: MasterModel = await master_service.get_by_master_id(message.master)
    except ObjectNotFoundError:
        logger.error(message.dict())
        create = MasterCreateSchema(
            master_id=message.master,
            title=message.master,
            salt_conf_pubkey=message.salt_conf_pubkey,
            sshfs_pubkey=message.sshfs_pubkey,
            pubkey=message.crypt_pubkey,
        )
        master = await master_service.create(create)
    else:
        if master.status is MasterStatus.keys_stale:
            master.status = MasterStatus.new
            master.pubkey = message.crypt_pubkey
            master.salt_conf_pubkey = message.salt_conf_pubkey
            master.sshfs_pubkey = message.sshfs_pubkey
            master = await master_service.update(query=master.id, data=master.model_dump())

    return CoreAuthResponse(
        master=master.master_id,
        crypt_pubkey=saltbox_crypt.pubkey,
        status=master.status,
    )


@router.subscriber('grains')
async def grains_handler(
    message: BridgeMinionGrainsMessage,
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
    message: BridgeMinionPresenceMessage,
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


@router.subscriber('burst_test_load')
async def burst_test_load_handler(message: BridgeTestBurstLoadMessage) -> None:
    # TODO (a.karmanov) : Count burst rate and save to DB
    ...
