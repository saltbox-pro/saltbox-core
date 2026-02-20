from faststream import Context, Logger
from faststream.redis import RedisRouter

from saltbox_bridge_messages import (
    BridgeAuthRequest,
    BridgePillarDataRequest,
    BridgeSyncDoneMessage,
    BridgeTestBurstLoadMessage,
    CoreAuthResponse,
    CorePillarDataResponse,
    MasterStatus,
)
from saltbox_core.event_bus.redis.master_bus_middlewares import MastersAuthMiddleware
from saltbox_core.masters.schemas.master_schemas import MasterCreateSchema, MasterModel
from saltbox_core.masters.services.master_service import MasterService
from saltbox_core.pillars.services.pillar import PillarService
from saltbox_sdk.exceptions import ObjectNotFoundException

router_not_auth = RedisRouter(prefix='master_', middlewares=[])
router = RedisRouter(prefix='master_', middlewares=[MastersAuthMiddleware])


@router_not_auth.subscriber('auth', middlewares=[])
async def auth(
    message: BridgeAuthRequest,
    master_service: MasterService = Context(),  # noqa: B008
) -> CoreAuthResponse:
    try:
        master: MasterModel = await master_service.get_by_master_id(message.master)
    except ObjectNotFoundException:
        create = MasterCreateSchema(
            master_id=message.master,
            title=message.master,
            salt_conf_pubkey=message.salt_conf_pubkey,
            sshfs_pubkey=message.sshfs_pubkey,
        )
        master = await master_service.create(create)
    else:
        if master.status is MasterStatus.KEYS_STALE:
            master.status = MasterStatus.NEW
            master.salt_conf_pubkey = message.salt_conf_pubkey
            master.sshfs_pubkey = message.sshfs_pubkey
            master = await master_service.update(query=master.id, data=master.model_dump())

    return CoreAuthResponse(
        master=master.master_id,
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


@router.subscriber('burst_test_load')
async def burst_test_load_handler(message: BridgeTestBurstLoadMessage) -> None:
    # TODO (a.karmanov) : Count burst rate and save to DB
    ...


@router.subscriber('get_pillar_data')
async def get_pillar_data_handler(
    message: BridgePillarDataRequest,
    logger: Logger,
    pillar_service: PillarService = Context(),  # noqa: B008
) -> CorePillarDataResponse:
    logger.debug(
        'Received pillar data request for minion %s from master %s, pillarenv %s',
        message.minion_id,
        message.master,
        message.pillarenv,
    )
    error = None
    pillars = {}
    try:
        pillars = await pillar_service.get_for_minion(
            master=message.master,
            minion_id=message.minion_id,
            pillarenv=message.pillarenv,
        )
    except ObjectNotFoundException:
        logger.warning('Minion with master %s and id %s not found', message.master, message.minion_id)
        pillars = {}
        error = 'Minion not found'
    except Exception as e:
        logger.error(
            'Error while getting pillar data for minion %s from master %s: %s', message.minion_id, message.master, e
        )
        error = 'Unknown error. Please check FastStream logs for details.'

    return CorePillarDataResponse(master=message.master, pillars=pillars, error=error)
