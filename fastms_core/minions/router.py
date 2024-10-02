import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from motor.core import AgnosticDatabase

from fastms_core.config import LOG_CONFIG
from fastms_core.db.mongo import get_db
from fastms_core.minions.models import Minion
from fastms_core.minions.crud import minion_crud
from fastms_core.minions.schemas import MinionSchema, MinionSchemaCreate, MinionSchemaUpdate
from fastms_core.redis import RedisDependency

logging.config.dictConfig(LOG_CONFIG.model_dump())

logger = logging.getLogger(__name__)

mongo_db_dep = Annotated[AgnosticDatabase, Depends(get_db)]

router = APIRouter(
    prefix='/minions',
    tags=['mongo'],
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
            prepared_grains = {k.decode(): json.loads(v) for k, v in grains.items() if k != b'id'}
            prepared_grains['efi_secure_boot'] = prepared_grains.get('efi-secure-boot')
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
            'name': 'grains.os_family',
            'label': 'OS Family',
        },
    ]
    return fields
