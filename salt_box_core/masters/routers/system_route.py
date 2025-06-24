import logging.config
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import PlainTextResponse
from saltbox_bridge_messages import BridgeTestBurstResponse, CoreTestBurstRequest

from salt_box_core.config import LOG_CONFIG, SETTINGS
from salt_box_core.db.exceptions import ObjectNotFoundError
from salt_box_core.event_bus.masters_bus import send_message_and_wait_response_to_master
from salt_box_core.http_errors import BadRequest, NotFound
from salt_box_core.masters.services.master_service import MasterService, get_master_service

logging.config.dictConfig(LOG_CONFIG.model_dump())

logger = logging.getLogger(__name__)


router = APIRouter(
    prefix='/system',
    tags=['System'],
    responses={status.HTTP_404_NOT_FOUND: {'description': 'Not found'}},
)


@router.get('/{user}/authorized_keys', operation_id='authorized_keys', response_class=PlainTextResponse)
async def authorized_keys(
    user: str,
    master_service: Annotated[MasterService, Depends(get_master_service)],
) -> str:
    masters = await master_service.get_accepted_list()
    if user == SETTINGS.sshfs_user:
        attr = 'sshfs_pubkey'
    elif user == SETTINGS.salt_conf_user:
        attr = 'gitfs_pubkey'
    else:
        msg = f'Unknown user {user}'
        raise BadRequest(msg)
    keys = [str(getattr(master, attr)) for master in masters]
    return '\n'.join(keys)


@router.post('/{master}/burst_test')
async def burst_test(
    master_id: str,
    master_service: Annotated[MasterService, Depends(get_master_service)],
    count: int = 100,
    size: int = 0,
) -> BridgeTestBurstResponse:
    try:
        await master_service.get_by_master_id(master_id)
    except ObjectNotFoundError:
        msg = f"Not found master_id='{master_id}'"
        raise NotFound(msg) from None
    message = CoreTestBurstRequest(master=master_id, count=count, size=size)
    # TODO (a.karmanov) : Run async, keep result in DB
    try:
        resp = await send_message_and_wait_response_to_master(message, message_tag='burst_test')
    except TimeoutError:
        msg = 'Execution is too long, try lesser count of load size or wait master to boot'
        raise BadRequest(msg) from None
    return BridgeTestBurstResponse(**resp)
