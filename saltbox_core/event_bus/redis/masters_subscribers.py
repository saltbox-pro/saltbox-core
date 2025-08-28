from datetime import UTC, datetime

from faststream import Context
from faststream.redis import RedisRouter

from saltbox_bridge_messages import (
    BridgeAuthRequest,
    BridgeInventoryDataSavedMessage,
    BridgeMinionGrainsMessage,
    BridgeMinionPresenceMessage,
    BridgeSyncDoneMessage,
    BridgeTestBurstLoadMessage,
    CoreAuthResponse,
    MasterStatus,
)
from saltbox_core.config import SETTINGS, logger
from saltbox_core.event_bus.redis.master_bus_middlewares import MastersAuthMiddleware
from saltbox_core.inventory.schemas import InventoryMinionSpec, InventoryModelFab, get_proto_for_category
from saltbox_core.inventory.services import CachedInventoryServices
from saltbox_core.inventory.utilities import solve_path
from saltbox_core.jobs.faststream import FSJobServiceDependency
from saltbox_core.masters.schemas.master_schemas import MasterCreateSchema, MasterModel
from saltbox_core.masters.services.master_service import MasterService
from saltbox_core.minion_collections.schemas.minion_schemas import (
    GrainsSchema,
    MinionCreateSchema,
    MinionModel,
    MinionUpdateSchema,
)
from saltbox_core.minion_collections.services.minion_service import MinionService
from saltbox_core.utilities.gpg import SaltBoxCrypt
from saltbox_core.utilities.jid import JID
from saltbox_sdk.exceptions import ObjectNotFoundException
from saltbox_sdk.faststream_utils.dependencies import FSMongoDependency

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
    except ObjectNotFoundException:
        create = MasterCreateSchema(
            master_id=message.master,
            title=message.master,
            salt_conf_pubkey=message.salt_conf_pubkey,
            sshfs_pubkey=message.sshfs_pubkey,
            pubkey=message.crypt_pubkey,
        )
        master = await master_service.create(create)
    else:
        if master.status is MasterStatus.KEYS_STALE:
            master.status = MasterStatus.NEW
            master.pubkey = message.crypt_pubkey
            master.salt_conf_pubkey = message.salt_conf_pubkey
            master.sshfs_pubkey = message.sshfs_pubkey
            master = await master_service.update(query=master.id, data=master.model_dump())

    return CoreAuthResponse(
        master=master.master_id,
        crypt_pubkey=saltbox_crypt.pubkey,
        status=master.status,
    )


@router.subscriber('sync_saltbox_done')
async def sync_saltbox_done(
    message: BridgeSyncDoneMessage,
    master_service: MasterService = Context(),  # noqa: B008
) -> None:
    master = await master_service.get_by_master_id(message.master)
    master.last_sync_timestamp = message.time
    master.last_sync_status = message.status
    await master_service.update(query=master.id, data=master.model_dump())


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
        except ObjectNotFoundException:
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
        except ObjectNotFoundException:
            logger.info('Minion "%s" from presence not found in DB', minion_id)


@router.subscriber('burst_test_load')
async def burst_test_load_handler(message: BridgeTestBurstLoadMessage) -> None:
    # TODO (a.karmanov) : Count burst rate and save to DB
    ...


async def _save_inventory(
    inventory_services: CachedInventoryServices,
    inventory: dict,
    minion_spec: InventoryMinionSpec,
) -> None:
    for category, inv_list in inventory.items():
        try:
            proto = get_proto_for_category(category)
            schema = InventoryModelFab.get_create_schema(proto)
        except TypeError as err:
            logger.warning(err)
            continue
        objects = [schema(**inv_item, minions=[minion_spec]) for inv_item in inv_list]
        await inventory_services.get(category).bulk_update_or_create(objects)


@router.subscriber('inventory_saved')
async def extract_inventory(
    message: BridgeInventoryDataSavedMessage,
    job_service: FSJobServiceDependency,
    mdb: FSMongoDependency,
) -> None:
    if not SETTINGS.module_inventory_on:
        return

    jid = JID(message.jid)
    inv_services = CachedInventoryServices(mdb)

    for minion_id in message.minions:
        minion_spec = InventoryMinionSpec(master_id=message.master, minion_id=minion_id)
        job_result = await job_service.get_job_return_for_minion(jid, minion_id)
        if job_result is not None:
            inventory = solve_path(message.path, job_result.model_dump(by_alias=True))
            await _save_inventory(inventory=inventory, inventory_services=inv_services, minion_spec=minion_spec)
        else:
            logger.warn('Not found inventory for minion %s, JID=%s', minion_spec, jid)
