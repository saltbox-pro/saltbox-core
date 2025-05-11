import logging.config
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from salt_box_core.config import LOG_CONFIG
from salt_box_core.db.exceptions import ObjectNotFoundError
from salt_box_core.db.mongo.schemas_base import PyObjectId
from salt_box_core.db.schemas_base import PaginatedResponse
from salt_box_core.http_errors import NotFound
from salt_box_core.masters.schemas.master_schemas import MasterModel, MasterQueryParams, MasterViewSchema
from salt_box_core.masters.services.master_service import MasterService, get_master_service

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


@router.post('/{mid}/accept', operation_id='task_accept')
async def master_accept(
    mid: PyObjectId,
    master_service: Annotated[MasterService, Depends(get_master_service)],
) -> MasterViewSchema:
    try:
        master: MasterModel = await master_service.accept(mid)

    except ObjectNotFoundError as e:
        raise NotFound(detail='Master not found') from e

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
