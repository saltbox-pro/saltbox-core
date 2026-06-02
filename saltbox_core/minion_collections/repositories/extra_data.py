from typing import Annotated, ClassVar

import pymongo
from fastapi import Depends
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.operations import _IndexKeyHint

from saltbox_core.minion_collections.schemas.extra_data import ExtraDataModel
from saltbox_sdk.db.mongo.config import get_mongo
from saltbox_sdk.db.mongo.repository_base import BaseMongoRepository


class ExtraDataRepository(BaseMongoRepository[ExtraDataModel]):
    class Meta:
        collection_name = 'minion_extra_data'
        auto_now_add_fields: ClassVar[list[str]] = ['created']
        auto_now_fields: ClassVar[list[str]] = ['modified']
        collection_index_to_keys: ClassVar[dict[str, _IndexKeyHint]] = {
            'category_and_data_unique_index_asc': [
                ('source', pymongo.ASCENDING),
                ('name', pymongo.ASCENDING),
                ('data', pymongo.ASCENDING),
            ],
            'data_index_wildecart': [('data.$**', pymongo.ASCENDING)],
        }


def get_extra_data_repository(
    db: Annotated[AsyncDatabase, Depends(get_mongo)],
) -> ExtraDataRepository:
    return ExtraDataRepository(db)
