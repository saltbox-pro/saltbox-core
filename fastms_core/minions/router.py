import json
import logging.config
from typing import Annotated, Any

from beanie import PydanticObjectId
from fastapi import APIRouter, HTTPException, Query, Response, status

from fastms_core.config import LOG_CONFIG
from fastms_core.db.mongo.schemas_base import PaginatedResponse
from fastms_core.minions.crud import minion_collection_crud, minion_crud
from fastms_core.minions.models import Minion
from fastms_core.minions.schemas import (
    MinionCollectionCreateSchema,
    MinionCollectionListQueryParams,
    MinionCollectionListSchema,
    MinionCollectionSchema,
    MinionCollectionUpdateSchema,
    MinionFilterValuesQueryParams,
    MinionListSchema,
    MinionsListQueryParams,
)
from fastms_core.minions.utils import make_aggregate_sequence
from fastms_core.utilities.model_schema import get_model_schema

logging.config.dictConfig(LOG_CONFIG.model_dump())

logger = logging.getLogger(__name__)


router = APIRouter(
    prefix='/minions',
    tags=['Minions'],
    responses={status.HTTP_404_NOT_FOUND: {'description': 'Not found'}},
)


# Minion filters views


@router.get('/filter-schema', operation_id='filter_schema')
async def filter_schema() -> list[dict[str, str]]:
    return get_model_schema(Minion)


@router.get('/filter-values', operation_id='filter_values')
async def unique_field_values(params: Annotated[MinionFilterValuesQueryParams, Query()]) -> dict[str, Any]:
    """Get unique values for a field in the Minion model"""
    search = json.loads(params.query)
    sequence = make_aggregate_sequence(params.field)

    result = await Minion.find(search).aggregate(sequence).to_list()
    response = {
        'total': len(result),
        'data': result,
    }
    return response


# Minion collections views


@router.get('/collection', operation_id='collections_list')
async def collections_list(
    params: Annotated[MinionCollectionListQueryParams, Query()],
) -> PaginatedResponse[MinionCollectionListSchema]:
    response = await minion_collection_crud.get_paginated(
        page=params.page, per_page=params.per_page, projection_model=MinionCollectionListSchema
    )
    return response


@router.post('/collection', operation_id='collection_create')
async def collection_create(item: MinionCollectionCreateSchema) -> MinionCollectionSchema:
    obj = await minion_collection_crud.create(obj_in=item)

    return MinionCollectionSchema.model_validate(obj)


@router.get('/collection/{cid}', operation_id='collection_retrieve')
async def collection_retrieve(cid: PydanticObjectId) -> MinionCollectionSchema:
    obj = await minion_collection_crud.get(id=cid)

    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    return MinionCollectionSchema.model_validate(obj)


@router.put('/collection/{cid}', operation_id='collection_update')
async def collection_update(cid: PydanticObjectId, item: MinionCollectionUpdateSchema) -> MinionCollectionSchema:
    obj = await minion_collection_crud.get(id=cid)

    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    obj_out = await minion_collection_crud.update(db_obj=obj, obj_in=item)

    return MinionCollectionSchema.model_validate(obj_out)


@router.delete('/collection/{cid}', operation_id='collection_delete', status_code=status.HTTP_204_NO_CONTENT)
async def collection_delete(cid: PydanticObjectId) -> Response:
    await minion_collection_crud.remove(id=cid)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# Minions views


@router.get('', operation_id='minions_list')
async def minions_list(
    params: Annotated[MinionsListQueryParams, Query()],
) -> PaginatedResponse[MinionListSchema]:
    search = json.loads(params.query)
    response = await minion_crud.get_paginated(
        search, page=params.page, per_page=params.per_page, projection_model=MinionListSchema
    )
    return response


@router.get('/{mid}', operation_id='minion_retrieve')
async def minion_retrieve(mid: PydanticObjectId) -> Minion:
    minion = await minion_crud.get(mid)
    if not minion:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Minion not found')
    return minion
