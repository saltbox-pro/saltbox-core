from typing import Annotated, Any, ClassVar

import pymongo
from fastapi import Depends
from pymongo.asynchronous.client_session import (
    AsyncClientSession as MongoAsyncClientSession,
)
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.asynchronous.database import AsyncDatabase as MongoAsyncDatabase
from pymongo.operations import _IndexKeyHint

from saltbox_core.minion_collections.repositories.extra_data_category import (
    ExtraDataCategoryRepository,
    get_extra_data_category_repository,
)
from saltbox_core.minion_collections.schemas.extra_data import ExtraDataModel
from saltbox_sdk.db.mongo.config import get_mongo
from saltbox_sdk.db.mongo.repository_base import BaseMongoRepository
from saltbox_sdk.db.mongo.schemas_base import PyObjectId


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
            'category_index_asc': [
                ('source', pymongo.ASCENDING),
                ('name', pymongo.ASCENDING),
            ],
            'category_by_minions_index_asc': [
                ('source', pymongo.ASCENDING),
                ('name', pymongo.ASCENDING),
                ('minions.minion_id', pymongo.ASCENDING),
            ],
            'data_index_wildecart': [('data.$**', pymongo.ASCENDING)],
            'minions_index_wildecart': [('minions.$**', pymongo.ASCENDING)],
            'minions_ids_index': [('minions.minion_id', pymongo.ASCENDING)],
        }

    def __init__(
        self,
        database: MongoAsyncDatabase[Any],
        extra_data_category_repository: ExtraDataCategoryRepository,
        **kwargs: Any,
    ) -> None:
        super().__init__(database=database, kwargs=kwargs)
        self.extra_data_category_repository = extra_data_category_repository

    async def get_minion_ids_by_filter(  # noqa: C901
        self,
        source: str,
        name: str,
        query: dict[str, Any],
        *,
        session: MongoAsyncClientSession | None = None,
    ) -> list[PyObjectId]:
        pipeline: list[dict[str, Any]] = [
            {'$match': {'source': source, 'name': name}},
        ]
        category = await self.extra_data_category_repository.get(query={'source': source, 'name': name})
        category_sub_queries: list[Any] = []
        minions_sub_queries: list[Any] = []

        def parse_query(_query: dict[str, Any]) -> None:  # noqa: C901
            for key, value in _query.items():
                if key.startswith('$'):
                    if isinstance(value, dict):
                        parse_query(value)
                    elif isinstance(value, list):
                        for item in value:
                            if isinstance(item, dict):
                                parse_query(item)
                else:
                    for category_field_name in category.category_fields:  # type: ignore
                        if key.startswith(category_field_name):
                            category_sub_queries.append({f'data.{key}': value})
                            break
                    for minion_field_name in category.minion_fields:
                        if key.startswith(minion_field_name):
                            minions_sub_queries.append({f'minions.data.{key}': value})
                            break

        parse_query(query)

        if len(category_sub_queries) == 1:
            pipeline.append({'$match': category_sub_queries[0]})
        elif len(category_sub_queries) > 0:
            pipeline.append({'$match': {'$or': category_sub_queries}})

        if len(minions_sub_queries) == 1:
            pipeline.append({'$match': minions_sub_queries[0]})
        elif len(minions_sub_queries) > 0:
            pipeline.append({'$match': {'$or': minions_sub_queries}})

        pipeline.extend(
            [
                {'$unwind': '$minions'},
                {
                    '$replaceRoot': {
                        'newRoot': {'$mergeObjects': ['$data', '$minions.data', {'_minion_key': '$minions.minion_id'}]}
                    }
                },
                {'$match': query},
                {'$group': {'_id': None, 'minion_ids': {'$addToSet': '$_minion_key'}}},
                {'$project': {'_id': 0, 'minion_ids': 1}},
            ]
        )

        raw_result = await (await self.collection.aggregate(pipeline=pipeline, session=session)).to_list()

        if not raw_result:
            return []

        return [PyObjectId(minion_id_str) for minion_id_str in raw_result[0]['minion_ids']]


def get_extra_data_repository(
    db: Annotated[AsyncDatabase, Depends(get_mongo)],
    extra_data_category_repository: Annotated[ExtraDataCategoryRepository, Depends(get_extra_data_category_repository)],
) -> ExtraDataRepository:
    return ExtraDataRepository(database=db, extra_data_category_repository=extra_data_category_repository)
