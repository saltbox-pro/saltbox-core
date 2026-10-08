from collections.abc import AsyncIterator
from typing import Annotated, Any, ClassVar

import pymongo
from fastapi import Depends
from pymongo.asynchronous.client_session import (
    AsyncClientSession as MongoAsyncClientSession,
)
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.asynchronous.database import AsyncDatabase as MongoAsyncDatabase
from pymongo.errors import DuplicateKeyError as MongoDuplicateKeyError
from pymongo.operations import _IndexKeyHint
from pymongo.results import UpdateResult

from saltbox_core.minion_collections.repositories.extra_data_category import (
    ExtraDataCategoryRepository,
    get_extra_data_category_repository,
)
from saltbox_core.minion_collections.schemas.extra_data import ExtraDataModel
from saltbox_sdk.db.mongo.aggregations import AnySearchAggregationStage
from saltbox_sdk.db.mongo.config import get_mongo
from saltbox_sdk.db.mongo.repository_base import BaseMongoRepository
from saltbox_sdk.db.mongo.schemas_base import PyObjectId, SortOrder
from saltbox_sdk.utilities.helpers import utc_now


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

    async def push_minions_entries(
        self,
        source: str,
        name: str,
        data: dict[str, Any],
        entries: list[dict[str, Any]],
        *,
        session: MongoAsyncClientSession | None = None,
    ) -> None:
        query = {'source': source, 'name': name, 'data': data}
        now = utc_now()
        update = {'$push': {'minions': {'$each': entries}}, '$set': {'modified': now}, '$setOnInsert': {'created': now}}

        try:
            await self.collection.update_one(query, update, upsert=True, session=session)
        except MongoDuplicateKeyError:
            await self.collection.update_one(query, update, upsert=True, session=session)

    async def pull_minions_entries(
        self,
        source: str,
        name: str,
        minion_ids: list[PyObjectId],
        *,
        is_system: bool,
        session: MongoAsyncClientSession | None = None,
    ) -> None:
        entry = {'minion_id': {'$in': minion_ids}, 'is_system': is_system}
        await self.collection.update_many(
            filter={'source': source, 'name': name, 'minions': {'$elemMatch': entry}},
            update={'$pull': {'minions': entry}, '$set': {'modified': utc_now()}},
            session=session,
        )

    async def get_minion_entry(
        self,
        source: str,
        name: str,
        minion_id: PyObjectId,
        entry_id: PyObjectId,
        *,
        session: MongoAsyncClientSession | None = None,
    ) -> dict[str, Any] | None:
        entry = {'_id': entry_id, 'minion_id': minion_id}
        doc = await self.collection.find_one(
            filter={'source': source, 'name': name, 'minions': {'$elemMatch': entry}},
            projection={'data': 1, 'minions.$': 1},
            session=session,
        )
        if doc is None:
            return None

        minion_entry = doc['minions'][0]
        return {**minion_entry, 'data': {**doc['data'], **minion_entry['data']}}

    async def set_manual_minion_entry_data(
        self,
        source: str,
        name: str,
        minion_id: PyObjectId,
        entry_id: PyObjectId,
        data: dict[str, Any],
        *,
        session: MongoAsyncClientSession | None = None,
    ) -> UpdateResult:
        manual_entry = {'_id': entry_id, 'minion_id': minion_id, 'is_system': False}
        now = utc_now()

        return await self.collection.update_one(
            filter={'source': source, 'name': name, 'minions': {'$elemMatch': manual_entry}},
            update={'$set': {'minions.$[entry].data': data, 'minions.$[entry].updated_at': now, 'modified': now}},
            array_filters=[{f'entry.{key}': value for key, value in manual_entry.items()}],
            session=session,
        )

    async def pull_manual_minion_entry(
        self,
        source: str,
        name: str,
        minion_id: PyObjectId,
        entry_id: PyObjectId,
        *,
        session: MongoAsyncClientSession | None = None,
    ) -> UpdateResult:
        manual_entry = {'_id': entry_id, 'minion_id': minion_id, 'is_system': False}

        return await self.collection.update_one(
            filter={'source': source, 'name': name, 'minions': {'$elemMatch': manual_entry}},
            update={'$pull': {'minions': manual_entry}, '$set': {'modified': utc_now()}},
            session=session,
        )

    async def unset_minions_data_field(
        self, source: str, name: str, field_name: str, *, session: MongoAsyncClientSession | None = None
    ) -> None:
        await self.collection.update_many(
            filter={'source': source, 'name': name, f'minions.data.{field_name}': {'$exists': True}},
            update={'$unset': {f'minions.$[].data.{field_name}': ''}, '$set': {'modified': utc_now()}},
            session=session,
        )

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
                    for category_field_name in category.category_fields:
                        if key == category_field_name or key.startswith(f'{category_field_name}.'):
                            category_sub_queries.append({f'data.{key}': value})
                            break
                    for minion_field_name in category.minion_fields:
                        if key == minion_field_name or key.startswith(f'{minion_field_name}.'):
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

    @staticmethod
    def build_grouped_pipeline(
        *,
        minion_ids: list[PyObjectId],
        category_source: str,
        category_name: str,
        group_by_fields: list[str],
        search_str: str | None = None,
        escape_search_str: bool = True,
        sort: dict[str, SortOrder] | None = None,
    ) -> list[dict[str, Any]]:
        group_key: dict[str, Any] = {field: {'$ifNull': [f'$data.{field}', None]} for field in group_by_fields}
        group_key['_source'] = '$source'
        group_key['_name'] = '$name'

        pipeline: list[dict[str, Any]] = [
            {
                '$match': {
                    'source': category_source,
                    'name': category_name,
                    'minions.minion_id': {'$in': minion_ids},
                }
            },
            {
                '$project': {
                    '_group_key': group_key,
                    'minions': {
                        '$filter': {
                            'input': '$minions',
                            'as': 'm',
                            'cond': {'$in': ['$$m.minion_id', minion_ids]},
                        }
                    },
                }
            },
            {'$unwind': '$minions'},
            {'$group': {'_id': '$_group_key', '_minions': {'$addToSet': '$minions.minion_id'}}},
            {'$replaceRoot': {'newRoot': {'$mergeObjects': ['$_id', {'_minions_count': {'$size': '$_minions'}}]}}},
        ]

        if search_str:
            pipeline.append(AnySearchAggregationStage(search=search_str, escape=escape_search_str).render_stage())

        full_sort = {'_source': SortOrder.ASC, '_name': SortOrder.ASC, **(sort or {})}
        full_sort.update({field: SortOrder.ASC for field in group_by_fields if field not in full_sort})

        pipeline.append({'$sort': full_sort})

        return pipeline

    async def get_grouped_paginated(
        self,
        *,
        minion_ids: list[PyObjectId],
        category_source: str,
        category_name: str,
        group_by_fields: list[str],
        search_str: str | None = None,
        escape_search_str: bool = True,
        limit: int = 0,
        skip: int = 0,
        sort: dict[str, SortOrder] | None = None,
        session: MongoAsyncClientSession | None = None,
    ) -> tuple[int, list[dict[str, Any]]]:
        pipeline = self.build_grouped_pipeline(
            minion_ids=minion_ids,
            category_source=category_source,
            category_name=category_name,
            group_by_fields=group_by_fields,
            search_str=search_str,
            escape_search_str=escape_search_str,
            sort=sort,
        )

        return await self.aggregate_paginated(pipeline, skip, limit, session=session)

    async def iter_grouped(
        self,
        *,
        minion_ids: list[PyObjectId],
        category_source: str,
        category_name: str,
        group_by_fields: list[str],
        search_str: str | None = None,
        escape_search_str: bool = True,
        sort: dict[str, SortOrder] | None = None,
        session: MongoAsyncClientSession | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        pipeline = self.build_grouped_pipeline(
            minion_ids=minion_ids,
            category_source=category_source,
            category_name=category_name,
            group_by_fields=group_by_fields,
            search_str=search_str,
            escape_search_str=escape_search_str,
            sort=sort,
        )

        async for row in self.aggregate_iter(pipeline, session=session):
            yield row


def get_extra_data_repository(
    db: Annotated[AsyncDatabase, Depends(get_mongo)],
    extra_data_category_repository: Annotated[ExtraDataCategoryRepository, Depends(get_extra_data_category_repository)],
) -> ExtraDataRepository:
    return ExtraDataRepository(database=db, extra_data_category_repository=extra_data_category_repository)
