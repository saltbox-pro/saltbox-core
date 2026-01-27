from typing import Annotated, ClassVar

from fastapi import Depends
from pymongo import ASCENDING
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.operations import _IndexKeyHint

from saltbox_sdk.db.migration_schemas import MigrationState
from saltbox_sdk.db.mongo.config import get_mongo
from saltbox_sdk.db.mongo.repository_base import BaseMongoRepository


class MongoMigrationStateRepository(BaseMongoRepository[MigrationState]):
    class Meta:
        collection_name: ClassVar[str] = '_migrations'
        collection_index_to_keys: ClassVar[dict[str, _IndexKeyHint]] = {
            'migration_id_unique_index_asc': [('id', ASCENDING)]
        }


def get_mongo_migration_repository(db: Annotated[AsyncDatabase, Depends(get_mongo)]) -> MongoMigrationStateRepository:
    return MongoMigrationStateRepository(db)
