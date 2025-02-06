from typing import Annotated, ClassVar

from fastapi import Depends
from pymongo.asynchronous.database import AsyncDatabase

from fastms_core.db.mongo.config import get_mongo
from fastms_core.db.mongo.repository_base import BaseMongoRepository
from fastms_core.minion_collections.schemas.collection_schemas import CollectionModel


class CollectionRepository(BaseMongoRepository[CollectionModel]):
    class Meta:
        collection_name = 'minion_collections'
        auto_now_add_fields: ClassVar[list[str]] = ['created']
        auto_now_fields: ClassVar[list[str]] = ['modified']


def get_collection_repository(db: Annotated[AsyncDatabase, Depends(get_mongo)]) -> CollectionRepository:
    return CollectionRepository(db)
