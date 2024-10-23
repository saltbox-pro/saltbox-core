from __future__ import annotations

import json
import logging

from beanie import PydanticObjectId
from fastapi import APIRouter, HTTPException

from fastms_core.config import LOG_CONFIG
from fastms_core.db.mongo.schemas_base import PaginatedResponse
from fastms_core.db.redis import RedisDependency
from fastms_core.minions.crud import minion_crud
from fastms_core.minions.models import Minion
from fastms_core.minions.schemas import MinionListSchema, MinionSchemaCreate
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
    rdb: RedisDependency,
    page: int = 0,
    per_page: int = 20,
    query: str | None = None,
) -> PaginatedResponse[MinionListSchema]:
    # Update minions from redis before getting them
    cursor = 0
    while True:
        cursor, data = await rdb.scan(cursor=cursor, match='minion:*:grains')
        for key in data:
            grains: dict[bytes, bytes] = await rdb.hgetall(name=key)

            # FIXME: Temporary solution to delete data from redis
            await rdb.delete(key)

            minion_id = key.decode().split(':')[1]
            prepared_grains = {k.decode(): json.loads(v) for k, v in grains.items()}
            minion_obj = {
                'minion_id': minion_id,
                'master': prepared_grains.get('master', ''),
                'grains': prepared_grains,
            }

            if prepared_grains:
                exist = await Minion.find_one({'minion_id': minion_id})
                if exist:
                    await minion_crud.update(db_obj=exist, obj_in=minion_obj)
                else:
                    await minion_crud.create(obj_in=MinionSchemaCreate(**minion_obj))

        # if data:
        #     await rdb.delete(*data)

        if not cursor:
            break

    # from str to dict
    search = json.loads(query) if query else {}
    response = await minion_crud.get_paginated(search, page=page, per_page=per_page, projection_model=MinionListSchema)
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
