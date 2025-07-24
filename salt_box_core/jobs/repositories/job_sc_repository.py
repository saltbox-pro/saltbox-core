from typing import Annotated, ClassVar

from fastapi import Depends
from pymongo.asynchronous.database import AsyncDatabase

from salt_box_core.jobs.schemas.job_sc_schemas import JobSchemaModel
from saltbox_sdk.db.mongo.config import get_mongo
from saltbox_sdk.db.mongo.repository_base import BaseMongoRepository


class JobSchemaRepository(BaseMongoRepository[JobSchemaModel]):
    class Meta:
        collection_name = 'job_schemas'
        auto_now_add_fields: ClassVar[list[str]] = ['created']
        auto_now_fields: ClassVar[list[str]] = ['modified']


def get_job_schema_repository(db: Annotated[AsyncDatabase, Depends(get_mongo)]) -> JobSchemaRepository:
    return JobSchemaRepository(db)
