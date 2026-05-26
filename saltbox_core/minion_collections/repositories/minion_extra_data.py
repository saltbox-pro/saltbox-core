from typing import Annotated, ClassVar

import pymongo
from fastapi import Depends
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.operations import _IndexKeyHint

from saltbox_core.minion_collections.schemas.minion_extra_data import MinionExtraDataItemModel
from saltbox_sdk.db.mongo.config import get_mongo
from saltbox_sdk.db.mongo.repository_base import BaseMongoRepository


class MinionExtraDataItemRepository(BaseMongoRepository[MinionExtraDataItemModel]):
    class Meta:
        collection_name = 'minion_extra_data_item'
        auto_now_add_fields: ClassVar[list[str]] = ['created']
        auto_now_fields: ClassVar[list[str]] = ['modified']
        collection_index_to_keys: ClassVar[dict[str, _IndexKeyHint]] = {
            'category_value_unique_index_asc': [
                ('source', pymongo.ASCENDING),
                ('name', pymongo.ASCENDING),
                ('value', pymongo.ASCENDING),
            ],
            'value_index_asc': [('value', pymongo.ASCENDING)],
        }


def get_minion_extra_data_item_repository(
    db: Annotated[AsyncDatabase, Depends(get_mongo)],
) -> MinionExtraDataItemRepository:
    return MinionExtraDataItemRepository(db)
