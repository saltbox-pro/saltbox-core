from __future__ import annotations

import asyncio
import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, WebSocket
from motor.core import AgnosticDatabase
from redis.asyncio.client import PubSub

from fastms_core import http_errors
from fastms_core.config import LOG_CONFIG
from fastms_core.db.mongo import get_db
from fastms_core.db.redis import RedisDependency
from fastms_core.minions.crud import minion_crud
from fastms_core.minions.schemas import MinionSchema, MinionSchemaCreate, MinionSchemaUpdate
from fastms_core.utilities.websocket import IsSocketDisconnected

logging.config.dictConfig(LOG_CONFIG.model_dump())

logger = logging.getLogger(__name__)

mongo_db_dep = Annotated[AgnosticDatabase, Depends(get_db)]

router = APIRouter(
    prefix='/minions',
    tags=['Minions'],
    responses={404: {'description': 'Not found'}},
)


@router.get('')
async def get_all_minions(
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


@router.get('/{mid}')
async def get_minion(mid: str, mdb: mongo_db_dep) -> MinionSchema:
    minion = await minion_crud.get_by_id(mdb, minion_id=mid)
    if not minion:
        raise http_errors.NotFound(detail=f'Minion {mid} not found')
    return MinionSchema(**minion.model_dump())


@router.get('/filter-schema')
async def get_minion_schema() -> list[dict]:
    # fields = Minion.model_json_schema()
    fields = [
        {
            'name': 'minion_id',
            'label': 'Minion ID',
        },
        {
            'name': 'master',
            'label': 'Master',
        },
        {
            'name': 'grains.host',
            'label': 'Host',
        },
        {
            'name': 'grains.fqdn',
            'label': 'FQDN',
        },
    ]
    return fields


@router.get('/have_grains')
async def list_minions_with_grains(rdb: RedisDependency) -> list[str]:
    """
    Get list of minions for which grains are kept in DB
    """

    def get_mid(value: bytes) -> str:
        return value.decode().removeprefix('minion:').removesuffix(':grains')

    result: list[str] = []
    cursor = 0
    while True:
        cursor, data = await rdb.scan(cursor=cursor, match='minion:*:grains')
        result.extend(map(get_mid, data))
        if not cursor:
            break
    return result


@router.get('/{mid}/grains', deprecated=True)
async def get_minion_grains_endpoint(mid: str, rdb: RedisDependency) -> dict[str, Any]:
    data = await rdb.hgetall(name=f'minion:{mid}:grains')
    if not data:
        msg = f'No grains kept for {mid}'
        raise http_errors.NotFound(msg)
    try:
        return {k: json.loads(val) for k, val in data.items()}
    except json.JSONDecodeError:
        msg = 'Failed to serialize value'
        raise http_errors.InternalServerError(msg) from None


@router.get('/{mid}/grain/{grain}', deprecated=True)
async def get_minion_the_grain_endpoint(mid: str, grain: str, rdb: RedisDependency) -> Any:
    """
    Get specific minion grain

    There are 404 for null value
    """
    value = await rdb.hget(name=f'minion:{mid}:grains', key=grain)
    if value is None:
        msg = f'No grain {grain} value for {mid}'
        raise http_errors.NotFound(msg)
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        msg = 'Failed to serialize value'
        raise http_errors.InternalServerError(msg) from None


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
