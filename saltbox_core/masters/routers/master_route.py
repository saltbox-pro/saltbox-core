import logging.config
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from saltbox_core.config import LOG_CONFIG
from saltbox_core.event_bus.masters_bus import notify_master_on_repos_update
from saltbox_core.masters.schemas.master_schemas import MasterModel, MasterQueryParams, MasterViewSchema
from saltbox_core.masters.services.master_service import MasterService, get_master_service
from saltbox_sdk.db.exceptions import ObjectNotFoundError
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.db.schemas_base import PaginatedResponse
from saltbox_sdk.http_errors import NotFound

logging.config.dictConfig(LOG_CONFIG.model_dump())

logger = logging.getLogger(__name__)


router = APIRouter(
    prefix='/masters',
    tags=['Masters'],
    responses={status.HTTP_404_NOT_FOUND: {'description': 'Not found'}},
)


@router.get('', operation_id='masters_list')
async def masters_list(
    params: Annotated[MasterQueryParams, Query()],
    master_service: Annotated[MasterService, Depends(get_master_service)],
) -> PaginatedResponse[MasterViewSchema]:
    query = params.model_dump(exclude={'skip', 'limit'}, exclude_none=True, exclude_unset=True)

    master_list: PaginatedResponse[MasterViewSchema] = await master_service.get_list_paginated(
        query=query,
        limit=params.limit,
        skip=params.skip,
        projection_model=MasterViewSchema,
    )

    return master_list


@router.get('/{master_id}', operation_id='master_get')
async def master_get(
    master_id: str,
    master_service: Annotated[MasterService, Depends(get_master_service)],
) -> MasterViewSchema:
    try:
        master: MasterModel = await master_service.get_by_master_id(master_id)
    except ObjectNotFoundError as e:
        raise NotFound(detail='Master not found') from e
    return MasterViewSchema.model_validate({'_id': master.id, **master.model_dump(by_alias=True)})


@router.post('/{mid}/accept', operation_id='task_accept')
async def master_accept(
    mid: PyObjectId,
    master_service: Annotated[MasterService, Depends(get_master_service)],
) -> MasterViewSchema:
    try:
        master: MasterModel = await master_service.accept(mid)

    except ObjectNotFoundError as err:
        raise NotFound(detail='Master not found') from err

    await notify_master_on_repos_update(master)
    return MasterViewSchema.model_validate({'_id': master.id, **master.model_dump(by_alias=True)})


@router.post('/{mid}/reject', operation_id='task_reject')
async def master_reject(
    mid: PyObjectId,
    master_service: Annotated[MasterService, Depends(get_master_service)],
) -> MasterViewSchema:
    try:
        master: MasterModel = await master_service.reject(mid)
    except ObjectNotFoundError as e:
        raise NotFound(detail='Master not found') from e

    return MasterViewSchema.model_validate({'_id': master.id, **master.model_dump(by_alias=True)})
