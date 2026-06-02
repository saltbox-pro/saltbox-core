from typing import Annotated, ClassVar

import pymongo
from fastapi import Depends
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.operations import _IndexKeyHint

from saltbox_core.minion_collections.schemas.extra_data_category import ExtraDataCategoryModel
from saltbox_sdk.db.mongo.config import get_mongo
from saltbox_sdk.db.mongo.repository_base import BaseMongoRepository


class ExtraDataCategoryRepository(BaseMongoRepository[ExtraDataCategoryModel]):
    class Meta:
        collection_name = 'minion_extra_data_category'
        auto_now_add_fields: ClassVar[list[str]] = ['created']
        auto_now_fields: ClassVar[list[str]] = ['modified']
        collection_index_to_keys: ClassVar[dict[str, _IndexKeyHint]] = {
            'source_and_name_unique_index_asc': [
                ('source', pymongo.ASCENDING),
                ('name', pymongo.ASCENDING),
            ],
        }


def get_extra_data_category_repository(
    db: Annotated[AsyncDatabase, Depends(get_mongo)],
) -> ExtraDataCategoryRepository:
    return ExtraDataCategoryRepository(db)
