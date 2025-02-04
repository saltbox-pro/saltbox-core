from typing import Annotated

from fastapi import Depends
from pymongo.asynchronous.database import AsyncDatabase

from fastms_core.db.mongo.config import get_mongo
from fastms_core.db.mongo.repository_base import BaseMongoRepository
from fastms_core.minion_collections.schemas.collection_schemas import CollectionModel


class CollectionRepository(BaseMongoRepository[CollectionModel]):
    class Meta:
        collection_name = 'minion_collections'


def get_collection_repository(db: Annotated[AsyncDatabase, Depends(get_mongo)]) -> CollectionRepository:
    return CollectionRepository(db)
