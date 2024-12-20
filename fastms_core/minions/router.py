import logging.config
from typing import Annotated

from beanie import PydanticObjectId
from fastapi import APIRouter, Body, HTTPException, status

from fastms_core.collections.crud import collections_crud
from fastms_core.collections.models import MinionCollection
from fastms_core.config import LOG_CONFIG
from fastms_core.db.mongo.schemas_base import PaginatedResponse
from fastms_core.minions.crud import minions_crud
from fastms_core.minions.models import Minion
from fastms_core.minions.schemas import (
    MinionFilterSchema,
    MinionFilterValuesQueryParams,
    MinionListSchema,
    MinionsListQueryParams,
    UniqueGrainValuesResponse,
)
from fastms_core.minions.utils import make_aggregate_sequence
from fastms_core.utilities.model_schema import get_model_schema

logging.config.dictConfig(LOG_CONFIG.model_dump())

logger = logging.getLogger(__name__)


minions_router = APIRouter(
    prefix='/minions',
    tags=['Minions'],
    responses={status.HTTP_404_NOT_FOUND: {'description': 'Not found'}},
)

filters_router = APIRouter(prefix='/filters', tags=['Filters'])


@minions_router.post('', operation_id='minions_list')
async def minions_list(
    params: Annotated[MinionsListQueryParams, Body()],
) -> PaginatedResponse[MinionListSchema]:
    search = params.query

    if params.collection_id:
        minions_collection = await collections_crud.get(params.collection_id)

        if isinstance(minions_collection, MinionCollection):
            search = {'$and': [minions_collection.query, search]}

    response = await minions_crud.get_paginated(
        search, page=params.page, per_page=params.per_page, projection_model=MinionListSchema
    )

    return response


@minions_router.get('/{mid}', operation_id='minion_retrieve')
async def minion_retrieve(mid: PydanticObjectId) -> Minion:
    minion = await minions_crud.get(mid)

    if not minion:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Minion not found')

    return minion


# Minion filters views


@filters_router.get('/schema', operation_id='filter_schema')
async def filter_schema() -> list[MinionFilterSchema]:
    return [MinionFilterSchema.model_validate(field) for field in get_model_schema(Minion)]


@filters_router.post('/unique-grain-values', operation_id='filter_values')
async def unique_field_values(params: Annotated[MinionFilterValuesQueryParams, Body()]) -> UniqueGrainValuesResponse:
    """Get unique values for a field in the Minion model"""
    sequence = make_aggregate_sequence(params.field)

    result = await Minion.find(params.query).aggregate(sequence).to_list()
    response = UniqueGrainValuesResponse(
        total=len(result),
        data=result,
    )
    return response
