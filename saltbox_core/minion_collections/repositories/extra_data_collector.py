from typing import Annotated, ClassVar

from fastapi import Depends
from pymongo.asynchronous.database import AsyncDatabase

from saltbox_core.minion_collections.schemas.extra_data_collector import ExtraDataCollectorModel
from saltbox_sdk.db.mongo.config import get_mongo
from saltbox_sdk.db.mongo.repository_base import BaseMongoRepository


class ExtraDataCollectorRepository(BaseMongoRepository[ExtraDataCollectorModel]):
    class Meta:
        collection_name = 'minion_extra_data_collector'
        auto_now_add_fields: ClassVar[list[str]] = ['created']
        auto_now_fields: ClassVar[list[str]] = ['modified']


def get_extra_data_collector_repository(
    db: Annotated[AsyncDatabase, Depends(get_mongo)],
) -> ExtraDataCollectorRepository:
    return ExtraDataCollectorRepository(db)
