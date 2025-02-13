from typing import Annotated, ClassVar

from fastapi import Depends
from pymongo.asynchronous.database import AsyncDatabase

from salt_box_core.db.mongo.config import get_mongo
from salt_box_core.db.mongo.repository_base import BaseMongoRepository
from salt_box_core.minion_collections.schemas.minion_schemas import MinionModel


class MinionRepository(BaseMongoRepository[MinionModel]):
    class Meta:
        collection_name = 'minions'
        auto_now_add_fields: ClassVar[list[str]] = ['created']
        auto_now_fields: ClassVar[list[str]] = ['modified']


def get_minion_repository(db: Annotated[AsyncDatabase, Depends(get_mongo)]) -> MinionRepository:
    return MinionRepository(db)
