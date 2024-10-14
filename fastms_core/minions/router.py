from __future__ import annotations

import asyncio
import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, WebSocket
from motor.core import AgnosticDatabase
from redis.asyncio.client import PubSub

from fastms_core import http_errors
from fastms_core.config import LOG_CONFIG
from fastms_core.db.mongo import get_db
from fastms_core.db.redis import RedisDependency
from fastms_core.minions.crud import minion_crud
from fastms_core.minions.models import Minion
from fastms_core.minions.schemas import MinionSchema, MinionSchemaCreate, MinionSchemaUpdate
from fastms_core.utilities.model_schema import get_model_schema
from fastms_core.utilities.websocket import IsSocketDisconnected

logging.config.dictConfig(LOG_CONFIG.model_dump())

logger = logging.getLogger(__name__)

mongo_db_dep = Annotated[AgnosticDatabase, Depends(get_db)]

router = APIRouter(
    prefix='/minions',
    tags=['Minions'],
    responses={404: {'description': 'Not found'}},
)


@router.get('', operation_id='minions_list')
async def minions_list(
    mdb: mongo_db_dep,
    rdb: RedisDependency,
    page: int = 0,
    per_page: int = 20,
    page_break: bool = False,
    query: str | None = None,
) -> list[MinionSchema]:
    # Update minions from redis before getting them
    cursor = 0
    while True:
        cursor, data = await rdb.scan(cursor=cursor, match='minion:*:grains')
        for key in data:
            grains: dict[bytes, bytes] = await rdb.hgetall(name=key)
            minion_id = key.decode().split(':')[1]
            prepared_grains = {k.decode(): json.loads(v) for k, v in grains.items()}
            minion_obj = {
                'minion_id': minion_id,
                'master': prepared_grains.get('master', ''),
                'grains': prepared_grains,
            }

            exist = await minion_crud.get_by_id(mdb, minion_id=minion_id)

            if exist:
                await minion_crud.update(mdb, db_obj=exist, obj_in=MinionSchemaUpdate(**minion_obj))
            else:
                await minion_crud.create(mdb, obj_in=MinionSchemaCreate(**minion_obj))
                # result.append(MinionSchema(**minion.model_dump()))

        if data:
            await rdb.delete(*data)

        if not cursor:
            break

    # from str to dict
    search = json.loads(query) if query else {}
    minions = await minion_crud.get_multi(mdb, search, page=page, per_page=per_page, page_break=page_break)

    return [MinionSchema(**minion.model_dump()) for minion in minions]


@router.get('/filter-schema', operation_id='filter_schema')
async def filter_schema() -> list[dict[str, str]]:
    return get_model_schema(Minion)


@router.get('/{mid}', operation_id='minion_retrieve')
async def minion_retrieve(mid: str, mdb: mongo_db_dep) -> MinionSchema:
    minion = await minion_crud.get_by_id(mdb, minion_id=mid)
    if not minion:
        raise http_errors.NotFound(detail=f'Minion {mid} not found')
    return MinionSchema(**minion.model_dump())


@router.websocket('/{mid}/grains')
async def minion_grains_websocket(
    mid: str,
    websocket: WebSocket,
    rdb: RedisDependency,
) -> None:
    await websocket.accept()

    async def reader(pubsub: PubSub) -> None:
        async for message in pubsub.listen():
            if message['type'] not in PubSub.PUBLISH_MESSAGE_TYPES:
                logger.debug('Skipping service message: %s', message)
                continue
            with IsSocketDisconnected(websocket) as disconnect:
                await websocket.send_text(message['data'].decode())
            if disconnect:
                return

    async with rdb.pubsub() as pubsub:
        await pubsub.psubscribe(f'minion:{mid}:grains')
        await asyncio.create_task(reader(pubsub))
