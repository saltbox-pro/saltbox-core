from faststream import Context
from faststream.redis import RedisRouter

from saltbox_bridge_messages import (
    BridgeAuthRequest,
    BridgeSyncDoneMessage,
    BridgeTestBurstLoadMessage,
    CoreAuthResponse,
    MasterStatus,
)
from saltbox_core.event_bus.redis.master_bus_middlewares import MastersAuthMiddleware
from saltbox_core.masters.schemas.master_schemas import MasterCreateSchema, MasterModel
from saltbox_core.masters.services.master_service import MasterService
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
