from typing import Annotated, Any, ClassVar

import pymongo
from fastapi import Depends
from pymongo.asynchronous.client_session import AsyncClientSession as MongoAsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.operations import _IndexKeyHint
from pymongo.results import UpdateResult

from saltbox_core.minion_collections.schemas.extra_data_category import ExtraDataCategoryModel
from saltbox_sdk.db.mongo.config import get_mongo
from saltbox_sdk.db.mongo.repository_base import BaseMongoRepository
from saltbox_sdk.utilities.helpers import utc_now


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

    async def push_field(
        self,
        source: str,
        name: str,
        field: dict[str, Any],
        *,
        is_minion_field: bool,
        session: MongoAsyncClientSession | None = None,
    ) -> UpdateResult:
        push: dict[str, Any] = {'fields': field}
        if is_minion_field:
            push['minion_fields'] = field['name']

        return await self.collection.update_one(
            filter={'source': source, 'name': name, 'is_system': False, 'fields.name': {'$ne': field['name']}},
            update={'$push': push, '$set': {'modified': utc_now()}},
            session=session,
        )

    async def pull_field(
        self, source: str, name: str, field_name: str, *, session: MongoAsyncClientSession | None = None
    ) -> UpdateResult:
        return await self.collection.update_one(
            filter={'source': source, 'name': name, 'is_system': False, 'fields.name': field_name},
            update={
                '$pull': {'fields': {'name': field_name}, 'minion_fields': field_name},
                '$set': {'modified': utc_now()},
            },
            session=session,
        )

    async def set_fields_order(
        self, source: str, name: str, field_names: list[str], *, session: MongoAsyncClientSession | None = None
    ) -> UpdateResult:
        names = {'$literal': field_names}
        ordered_fields = {
            '$map': {
                'input': names,
                'as': 'field_name',
                'in': {
                    '$arrayElemAt': [
                        {'$filter': {'input': '$fields', 'cond': {'$eq': ['$$this.name', '$$field_name']}}},
                        0,
                    ]
                },
            }
        }
        rest_fields = {'$filter': {'input': '$fields', 'cond': {'$not': [{'$in': ['$$this.name', names]}]}}}

        return await self.collection.update_one(
            filter={'source': source, 'name': name, 'is_system': False, 'fields.name': {'$all': field_names}},
            update=[{'$set': {'fields': {'$concatArrays': [ordered_fields, rest_fields]}, 'modified': utc_now()}}],
            session=session,
        )


def get_extra_data_category_repository(
    db: Annotated[AsyncDatabase, Depends(get_mongo)],
) -> ExtraDataCategoryRepository:
    return ExtraDataCategoryRepository(db)
