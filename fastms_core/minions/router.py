import json
import logging.config
from typing import Annotated, Any

from beanie import PydanticObjectId
from fastapi import APIRouter, HTTPException, Query

from fastms_core.config import LOG_CONFIG
from fastms_core.db.mongo.schemas_base import PaginatedResponse
from fastms_core.minions.crud import minion_crud
from fastms_core.minions.models import Minion
from fastms_core.minions.schemas import (
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
    responses={404: {'description': 'Not found'}},
)


@router.get('', operation_id='minions_list')
async def minions_list(
    params: Annotated[MinionsListQueryParams, Query()],
) -> PaginatedResponse[MinionListSchema]:
    search = json.loads(params.query)
    response = await minion_crud.get_paginated(
        search, page=params.page, per_page=params.per_page, projection_model=MinionListSchema
    )
    return response


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


@router.get('/{id}', operation_id='minion_retrieve')
async def minion_retrieve(id: PydanticObjectId) -> Minion:
    minion = await minion_crud.get(id)
    if not minion:
        raise HTTPException(status_code=404, detail='Minion not found')
    return minion
