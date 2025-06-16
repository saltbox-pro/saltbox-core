import logging.config
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import PlainTextResponse

from salt_box_core.config import LOG_CONFIG, SETTINGS
from salt_box_core.http_errors import BadRequest
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
    masters = await master_service.get_list(query={}, skip=0, limit=0)
    if user == SETTINGS.sshfs_user:
        attr = 'sshfs_pubkey'
    elif user == SETTINGS.salt_conf_user:
        attr = 'gitfs_pubkey'
    else:
        msg = f'Unknown user {user}'
        raise BadRequest(msg)
    keys = [str(getattr(master, attr)) for master in masters]
    return '\n'.join(keys)
