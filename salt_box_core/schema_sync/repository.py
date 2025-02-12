from typing import Annotated, ClassVar

from fastapi import Depends
from pymongo.asynchronous.database import AsyncDatabase

from salt_box_core.db.mongo.config import get_mongo
from salt_box_core.db.mongo.repository_base import BaseMongoRepository
from salt_box_core.schema_sync.schemas import JSONSchemaModel


class JSONSchemaRepository(BaseMongoRepository[JSONSchemaModel]):
    class Meta:
        collection_name = 'json_schemas'
        auto_now_add_fields: ClassVar[list[str]] = ['created']
        auto_now_fields: ClassVar[list[str]] = ['modified']


def get_json_schema_repository(db: Annotated[AsyncDatabase, Depends(get_mongo)]) -> JSONSchemaRepository:
    return JSONSchemaRepository(db)
