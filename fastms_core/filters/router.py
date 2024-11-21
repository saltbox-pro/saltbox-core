from __future__ import annotations

import logging.config
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status

from fastms_core.config import LOG_CONFIG
from fastms_core.db.mongo.schemas_base import PaginatedResponse
from fastms_core.filters.crud import filter_crud
from fastms_core.filters.schemas import (
    FilterSchema, FilterCreateSchema, FilterUpdateSchema, FilterListSchema, FilterListQueryParams
)

logging.config.dictConfig(LOG_CONFIG.model_dump())

logger = logging.getLogger(__name__)


router = APIRouter(
    prefix='/filters',
    tags=['Filters'],
    responses={404: {'description': 'Not found'}},
)


@router.get('', operation_id='filters_list')
async def filters_list(
    params: Annotated[FilterListQueryParams, Query()],
) -> PaginatedResponse[FilterListSchema]:
    response = await filter_crud.get_paginated(
        page=params.page, per_page=params.per_page, projection_model=FilterListSchema
    )
    return response


@router.post('', operation_id='filter_create')
async def filter_create(item: FilterCreateSchema) -> FilterSchema:
    obj = await filter_crud.create(obj_in=item)

    return FilterSchema.model_validate(obj)


@router.get('/{fid}', operation_id='filter_retrieve')
async def filter_retrieve(fid: str) -> FilterSchema:
    obj = await filter_crud.get(id=fid)

    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    return FilterSchema.model_validate(obj)


@router.put('/{fid}', operation_id='filter_update')
async def filter_update(fid: str, item: FilterUpdateSchema) -> FilterSchema:
    obj = await filter_crud.get(id=fid)

    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    obj_out = await filter_crud.update(db_obj=obj, obj_in=item)

    return FilterSchema.model_validate(obj_out)


@router.delete('/{fid}', operation_id='filter_delete', status_code=status.HTTP_204_NO_CONTENT)
async def filter_delete(fid: str):
    await filter_crud.remove(id=fid)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
