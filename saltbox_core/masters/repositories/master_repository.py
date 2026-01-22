from typing import Annotated, ClassVar

import pymongo
from fastapi import Depends
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.operations import _IndexKeyHint

from saltbox_core.masters.schemas.master_schemas import MasterModel
from saltbox_sdk.db.mongo.config import get_mongo
from saltbox_sdk.db.mongo.repository_base import BaseMongoRepository


class MasterRepository(BaseMongoRepository[MasterModel]):
    class Meta:
        collection_name = 'master'
        auto_now_add_fields: ClassVar[list[str]] = ['created']
        auto_now_fields: ClassVar[list[str]] = ['modified']
        collection_index_to_keys: ClassVar[dict[str, _IndexKeyHint]] = {
            'master_id_unique_index_asc': [('master_id', pymongo.ASCENDING)]
        }

    async def get_by_master_id(self, value: str) -> MasterModel:
        return await self.get(query={'master_id': value})


def get_master_repository(db: Annotated[AsyncDatabase, Depends(get_mongo)]) -> MasterRepository:
    return MasterRepository(db)
