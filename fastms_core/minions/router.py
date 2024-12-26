import logging.config

from beanie import PydanticObjectId
from fastapi import APIRouter, HTTPException, status
from pymongo.errors import PyMongoError

from fastms_core import http_errors
from fastms_core.collections.crud import collections_crud
from fastms_core.collections.models import MinionCollection
from fastms_core.config import LOG_CONFIG
from fastms_core.db.mongo.schemas_base import PaginatedResponse
from fastms_core.minions.crud import minions_crud
from fastms_core.minions.models import Minion
from fastms_core.minions.schemas import (
    MinionFilterSchema,
    MinionFilterValuesBody,
    MinionListSchema,
    MinionsListBody,
    UniqueGrainValuesResponse,
)
from fastms_core.minions.utils import MongoPiplineBuilder
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
    body: MinionsListBody,
) -> PaginatedResponse[MinionListSchema]:
    search = body.query

    if body.collection_id:
        minions_collection = await collections_crud.get(body.collection_id)

        if isinstance(minions_collection, MinionCollection):
            search = {'$and': [minions_collection.query, search]}

    try:
        return await minions_crud.get_paginated(
            search, page=body.page, per_page=body.per_page, projection_model=MinionListSchema
        )
    except PyMongoError as error:
        raise http_errors.UnprocessableEntity(str(error)) from error


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
async def unique_field_values(body: MinionFilterValuesBody) -> UniqueGrainValuesResponse:
    """Get unique values for a field in the Minion model"""
    pipline_builder = MongoPiplineBuilder(body.field)
    pipline = pipline_builder.build()

    try:
        result = await minions_crud.get_pipeline(body.query, pipeline=pipline)
    except PyMongoError as error:
        raise http_errors.UnprocessableEntity(str(error)) from error

    response = UniqueGrainValuesResponse(
        total=len(result),
        data=result,
    )

    return response
