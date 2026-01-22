from typing import Annotated, ClassVar

import pymongo
from fastapi import Depends
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.operations import _IndexKeyHint

from saltbox_core.jobs.schemas.job_schemas import JobModel
from saltbox_sdk.db.mongo.config import get_mongo
from saltbox_sdk.db.mongo.repository_base import BaseMongoRepository


class JobRepository(BaseMongoRepository[JobModel]):
    class Meta:
        collection_name = 'jobs'
        auto_now_add_fields: ClassVar[list[str]] = ['created']
        auto_now_fields: ClassVar[list[str]] = ['modified']
        collection_index_to_keys: ClassVar[dict[str, _IndexKeyHint]] = {
            'job_jid_index_asc': [('jid', pymongo.ASCENDING)],
            'jid_and_salt_master_unique_index_asc': [
                ('jid', pymongo.ASCENDING),
                ('salt_master', pymongo.ASCENDING)
            ]
        }


def get_job_repository(db: Annotated[AsyncDatabase, Depends(get_mongo)]) -> JobRepository:
    return JobRepository(db)
