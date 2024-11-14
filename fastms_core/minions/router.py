from __future__ import annotations

import json
import logging.config
from typing import Annotated

from beanie import PydanticObjectId
from fastapi import APIRouter, HTTPException, Query

from fastms_core.config import LOG_CONFIG
from fastms_core.db.mongo.schemas_base import PaginatedResponse
from fastms_core.minions.crud import minion_crud
from fastms_core.minions.models import Minion
from fastms_core.minions.schemas import MinionListSchema, MinionsListQueryParams
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


@router.get('/{id}', operation_id='minion_retrieve')
async def minion_retrieve(id: PydanticObjectId) -> Minion:
    minion = await minion_crud.get(id)
    if not minion:
        raise HTTPException(status_code=404, detail='Minion not found')
    return minion
