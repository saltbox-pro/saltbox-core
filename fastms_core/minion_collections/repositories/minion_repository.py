from typing import Annotated

from fastapi import Depends
from pymongo.asynchronous.database import AsyncDatabase

from fastms_core.db.mongo.config import get_mongo
from fastms_core.db.mongo.repository_base import BaseMongoRepository
from fastms_core.minion_collections.schemas.minion_schemas import MinionModel


class MinionRepository(BaseMongoRepository[MinionModel]):
    class Meta:
        collection_name = 'minions'


def get_minion_repository(db: Annotated[AsyncDatabase, Depends(get_mongo)]) -> MinionRepository:
    return MinionRepository(db)
