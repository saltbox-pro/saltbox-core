import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, ClassVar, cast, overload

import pymongo
from fastapi import Depends
from pymongo.asynchronous.client_session import AsyncClientSession as MongoAsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.asynchronous.database import AsyncDatabase as MongoAsyncDatabase
from pymongo.operations import UpdateOne, _IndexKeyHint
from pymongo.results import UpdateResult

from saltbox_core.minion_collections.exceptions import CyclicCollectionReferenceException
from saltbox_core.minion_collections.repositories.collection import CollectionRepository, get_collection_repository
from saltbox_core.minion_collections.repositories.extra_data import ExtraDataRepository, get_extra_data_repository
from saltbox_core.minion_collections.schemas.collection import CollectionBaseTreeModel
from saltbox_core.minion_collections.schemas.minion import MinionModel
from saltbox_core.minion_collections.utils.activity_filter import get_minion_active_dt, parse_bool_filter
from saltbox_core.minion_collections.utils.collection_filter import COLLECTION_FILTER_FIELD, parse_collection_filter
from saltbox_core.minion_collections.utils.unique_values import UniqueValueKind, build_unique_values_stages
from saltbox_sdk.db.mongo.aggregations import (
    AbstractAggregationStage,
    AddFieldsAggregationStage,
    AggregatedField,
    AggregationsStore,
    AnySearchAggregationStage,
    GroupAggregationStage,
    LookupAggregationStage,
    MatchAggregationStage,
    ProjectAggregationStage,
    UnsetAggregationStage,
    UnwindAggregationStage,
)
from saltbox_sdk.db.mongo.config import get_mongo
from saltbox_sdk.db.mongo.repository_base import BaseMongoRepository, ProjectionModel
from saltbox_sdk.db.mongo.schemas_base import PyObjectId, SortOrder
from saltbox_sdk.event_bus.schemas import ExtraDataCategoryType
from saltbox_sdk.exceptions import ObjectNotFoundException
from saltbox_sdk.utilities.helpers import utc_now

EXTRA_STATIC_DATA_AS_KV = {
    '$map': {
        'input': {'$objectToArray': {'$ifNull': ['$extra_static', {}]}},
        'as': 'src',
        'in': {
            'k': '$$src.k',
            'v': {
                '$arrayToObject': {
                    '$map': {
                        'input': {'$objectToArray': '$$src.v'},
                        'as': 'cat',
                        'in': {'k': '$$cat.k', 'v': {'$map': {'input': '$$cat.v', 'as': 'it', 'in': '$$it.data'}}},
                    }
                }
            },
        },
    }
}


class IsNotActiveAggregationStage(AbstractAggregationStage):
    def render_stage(self) -> dict[str, Any]:
        return {
            '$addFields': {
                'is_not_active': {
                    '$or': [
                        {'$eq': [{'$ifNull': ['$last_activity', None]}, None]},
                        {'$lt': ['$last_activity', get_minion_active_dt()]},
                    ]
                }
            }
        }


class MinionRepository(BaseMongoRepository[MinionModel]):
    def __init__(
        self,
        database: MongoAsyncDatabase[Any],
        extra_data_repository: ExtraDataRepository,
        collection_repository: CollectionRepository,
        **kwargs: Any,
    ) -> None:
        super().__init__(database=database)
        self.extra_data_repository = extra_data_repository
        self.collection_repository = collection_repository

    async def last_activity_seconds_query_override(
        self, field_name: str, field_match: re.Match, field_value: Any, full_raw_query: dict
    ) -> dict[str, Any]:
        field_name_override = 'last_activity'

        if isinstance(field_value, dict):
            lookup = cast(str, next(iter(field_value)))
            value = field_value[lookup]

            if lookup in ['$in', '$nin']:
                return {
                    field_name_override: {
                        lookup: [datetime.now(UTC) - timedelta(seconds=float(item_val)) for item_val in value]
                    }
                }
            else:
                lookup = {'$lt': '$gt', '$lte': '$gte', '$gt': '$lt', '$gte': '$lte'}.get(lookup, lookup)
                return {field_name_override: {lookup: datetime.now(UTC) - timedelta(seconds=float(value))}}
        else:
            return {field_name_override: datetime.now(UTC) - timedelta(seconds=float(field_value))}

    async def is_never_active_query_override(
        self, field_name: str, field_match: re.Match, field_value: Any, full_raw_query: dict
    ) -> dict[str, Any]:
        if parse_bool_filter(field_name, field_value):
            return {'last_activity': None}

        return {'last_activity': {'$ne': None}}

    async def is_not_active_query_override(
        self, field_name: str, field_match: re.Match, field_value: Any, full_raw_query: dict
    ) -> dict[str, Any]:
        active_dt = get_minion_active_dt()

        if parse_bool_filter(field_name, field_value):
            return {'last_activity': {'$not': {'$gte': active_dt}}}

        return {'last_activity': {'$gte': active_dt}}

    async def extra_static_query_override(
        self, field_name: str, field_match: re.Match, field_value: Any, full_raw_query: dict
    ) -> dict[str, Any]:
        source: str = field_match.group('source')
        name: str = field_match.group('name')
        sub_field: str = field_match.group('sub_field')
        field_path = f'extra_static.{source}.{name}.data.{sub_field}'

        try:
            category = await self.extra_data_repository.extra_data_category_repository.get(
                {'source': source, 'name': name}
            )
        except ObjectNotFoundException:
            return {field_path: field_value}

        return {field_path: category.cast_filter_value(field_name=sub_field, value=field_value)}

    async def extra_aggregated_query_override(
        self, field_name: str, field_match: re.Match, field_value: Any, full_raw_query: dict
    ) -> dict[str, Any]:
        source: str = field_match.group('source')
        name: str = field_match.group('name')
        sub_field: str = field_match.group('sub_field')

        category = await self.extra_data_repository.extra_data_category_repository.get({'source': source, 'name': name})
        cast_value = category.cast_filter_value(field_name=sub_field, value=field_value)

        minion_ids = await self.extra_data_repository.get_minion_ids_by_filter(
            source=source, name=name, query={sub_field: cast_value}
        )

        return {'_id': {'$in': minion_ids}}

    async def extra_query_override(
        self, field_name: str, field_match: re.Match, field_value: Any, full_raw_query: dict
    ) -> dict[str, Any]:
        source: str = field_match.group('source')
        name: str = field_match.group('name')

        category = await self.extra_data_repository.extra_data_category_repository.get({'source': source, 'name': name})

        if category.type == ExtraDataCategoryType.STATIC:
            return await self.extra_static_query_override(
                field_name=field_name, field_match=field_match, field_value=field_value, full_raw_query=full_raw_query
            )
        elif category.type == ExtraDataCategoryType.AGGREGATED:
            return await self.extra_aggregated_query_override(
                field_name=field_name, field_match=field_match, field_value=field_value, full_raw_query=full_raw_query
            )

        raise KeyError

    async def collection_query_override(
        self, field_name: str, field_match: re.Match, field_value: Any, full_raw_query: dict
    ) -> dict[str, Any]:
        return await self.__prepare_query__(await self._expand_collection_condition(field_value, parent_slugs=()))

    async def _expand_collection_condition(self, field_value: Any, *, parent_slugs: tuple[str, ...]) -> dict[str, Any]:
        lookup, slugs = parse_collection_filter(field_value)

        for slug in slugs:
            if slug in parent_slugs:
                raise CyclicCollectionReferenceException([*parent_slugs[parent_slugs.index(slug) :], slug])

        collections = await self.collection_repository.get_list(
            query={'slug': {'$in': slugs}}, projection_model=CollectionBaseTreeModel
        )
        queries = [
            await self._expand_query_collections(collection.full_query, parent_slugs=(*parent_slugs, collection.slug))
            for collection in collections
        ]

        if lookup == '$in':
            return {'$or': queries} if queries else {'_id': {'$in': []}}

        return {'$nor': queries} if queries else {}

    async def _expand_query_collections(self, query: Any, *, parent_slugs: tuple[str, ...]) -> Any:
        if isinstance(query, dict):
            expanded_query: dict[str, Any] = {}
            for key, value in query.items():
                if key == COLLECTION_FILTER_FIELD:
                    expanded_query.update(await self._expand_collection_condition(value, parent_slugs=parent_slugs))
                else:
                    expanded_query[key] = await self._expand_query_collections(value, parent_slugs=parent_slugs)
            return expanded_query

        if isinstance(query, list):
            return [await self._expand_query_collections(item, parent_slugs=parent_slugs) for item in query]

        return query

    @overload
    async def get_by_master_and_id(self, master: str, minion_id: str) -> MinionModel: ...

    @overload
    async def get_by_master_and_id(
        self, master: str, minion_id: str, projection_model: type[ProjectionModel]
    ) -> ProjectionModel: ...

    async def get_by_master_and_id(
        self, master: str, minion_id: str, projection_model: type[ProjectionModel] | None = None
    ) -> ProjectionModel | MinionModel:
        query = {'master': master, 'minion_id': minion_id}

        if projection_model:
            return await self.get(query=query, projection_model=projection_model)
        else:
            return await self.get(query=query)

    async def get_ids(
        self, query: dict[str, Any], *, session: MongoAsyncClientSession | None = None
    ) -> list[PyObjectId]:
        docs = await self.collection.find(filter=query, projection={'_id': 1}, session=session).to_list()
        return [doc['_id'] for doc in docs]

    async def get_grains_keys(self, query: dict[str, Any] | None) -> list[str]:
        query = await self.__prepare_query__(query)
        pipeline = await self.prepare_pipeline({'grains': 1}, query) or [{'$match': query or {}}]
        pipeline += [
            {
                '$project': {
                    'keys': {'$map': {'input': {'$objectToArray': {'$ifNull': ['$grains', {}]}}, 'in': '$$this.k'}}
                }
            },
            {'$group': {'_id': '$keys'}},
        ]

        keys: set[str] = set()
        for doc in await self.aggregate(pipeline):
            keys.update(doc['_id'])

        return sorted(keys)

    async def get_unique_grain_values(
        self,
        query: dict[str, Any],
        grain: str,
        kind: UniqueValueKind,
        skip: int = 0,
        limit: int = 0,
        *,
        session: MongoAsyncClientSession | None = None,
    ) -> tuple[int, list[dict[str, Any]]]:
        pipeline = [{'$match': query}, *build_unique_values_stages(f'grains.{grain}', '_id', kind)]

        return await self.aggregate_paginated(pipeline, skip, limit, session=session)

    async def get_targeting_masters(
        self,
        query: dict[str, Any],
        sort: dict[str, SortOrder] | None = None,
        *,
        session: MongoAsyncClientSession | None = None,
    ) -> list[dict[str, Any]]:
        pipeline: list[dict[str, Any]] = [
            {'$match': query},
            {'$group': {'_id': '$master', 'minions_count': {'$sum': 1}}},
            {'$lookup': {'from': 'master', 'localField': '_id', 'foreignField': 'master_id', 'as': 'master'}},
            {'$unwind': {'path': '$master', 'preserveNullAndEmptyArrays': True}},
            {
                '$project': {
                    '_id': 0,
                    'master_id': '$_id',
                    'title': '$master.title',
                    'status': '$master.status',
                    'minions_count': 1,
                }
            },
            {'$sort': dict(sort) if sort else {'master_id': 1}},
        ]

        return await self.aggregate(pipeline, session=session)

    async def get_unique_static_extra_values(
        self,
        query: dict[str, Any],
        source: str,
        name: str,
        field_name: str,
        kind: UniqueValueKind,
        skip: int = 0,
        limit: int = 0,
        *,
        session: MongoAsyncClientSession | None = None,
    ) -> tuple[int, list[dict[str, Any]]]:
        field_path = f'extra_static.{source}.{name}'
        pipeline: list[dict[str, Any]] = [
            {'$match': query},
            {'$unwind': f'${field_path}'},
            *build_unique_values_stages(f'{field_path}.data.{field_name}', '_id', kind),
        ]

        return await self.aggregate_paginated(pipeline, skip, limit, session=session)

    async def get_static_extra_data_item(
        self,
        minion_id: PyObjectId,
        source: str,
        name: str,
        item_id: PyObjectId,
        *,
        session: MongoAsyncClientSession | None = None,
    ) -> dict[str, Any] | None:
        field_path = f'extra_static.{source}.{name}'
        doc = await self.collection.find_one(filter={'_id': minion_id}, projection={field_path: 1}, session=session)
        items = ((doc or {}).get('extra_static') or {}).get(source, {}).get(name) or []

        return next((item for item in items if item.get('_id') == item_id), None)

    async def push_static_extra_data_items(
        self,
        source: str,
        name: str,
        items_by_minion: dict[PyObjectId, list[dict[str, Any]]],
        *,
        session: MongoAsyncClientSession | None = None,
    ) -> None:
        field_path = f'extra_static.{source}.{name}'
        now = utc_now()
        operations: list[UpdateOne] = []

        for minion_id, items in items_by_minion.items():
            update = {'$push': {field_path: {'$each': items}}, '$set': {'modified': now}}
            operations.append(UpdateOne({'_id': minion_id}, update))

        await self.collection.bulk_write(operations, session=session)

    async def replace_static_extra_data_items(
        self,
        source: str,
        name: str,
        items_by_minion: dict[PyObjectId, list[dict[str, Any]]],
        *,
        is_system: bool,
        session: MongoAsyncClientSession | None = None,
    ) -> None:
        field_path = f'extra_static.{source}.{name}'
        now = utc_now()
        kept_items = {
            '$filter': {
                'input': {'$ifNull': [f'${field_path}', []]},
                'cond': {'$ne': ['$$this.is_system', is_system]},
            }
        }
        operations: list[UpdateOne] = []

        for minion_id, items in items_by_minion.items():
            update = [{'$set': {field_path: {'$concatArrays': [kept_items, {'$literal': items}]}, 'modified': now}}]
            operations.append(UpdateOne({'_id': minion_id}, update))

        await self.collection.bulk_write(operations, session=session)

    async def set_manual_static_extra_data_item_data(
        self,
        minion_id: PyObjectId,
        source: str,
        name: str,
        item_id: PyObjectId,
        data: dict[str, Any],
        *,
        session: MongoAsyncClientSession | None = None,
    ) -> UpdateResult:
        field_path = f'extra_static.{source}.{name}'
        manual_item = {'_id': item_id, 'is_system': False}
        now = utc_now()

        return await self.collection.update_one(
            filter={'_id': minion_id, field_path: {'$elemMatch': manual_item}},
            update={
                '$set': {f'{field_path}.$[item].data': data, f'{field_path}.$[item].updated_at': now, 'modified': now}
            },
            array_filters=[{f'item.{key}': value for key, value in manual_item.items()}],
            session=session,
        )

    async def pull_manual_static_extra_data_item(
        self,
        minion_id: PyObjectId,
        source: str,
        name: str,
        item_id: PyObjectId,
        *,
        session: MongoAsyncClientSession | None = None,
    ) -> UpdateResult:
        field_path = f'extra_static.{source}.{name}'
        manual_item = {'_id': item_id, 'is_system': False}

        return await self.collection.update_one(
            filter={'_id': minion_id, field_path: {'$elemMatch': manual_item}},
            update={'$pull': {field_path: manual_item}, '$set': {'modified': utc_now()}},
            session=session,
        )

    async def unset_static_category_field(
        self, source: str, name: str, *, session: MongoAsyncClientSession | None = None
    ) -> None:
        field_path = f'extra_static.{source}.{name}'
        await self.collection.update_many(
            filter={field_path: {'$exists': True}},
            update={'$unset': {field_path: ''}},
            session=session,
        )

    async def remove_static_category_data_field(
        self, source: str, name: str, field_name: str, *, session: MongoAsyncClientSession | None = None
    ) -> None:
        field_path = f'extra_static.{source}.{name}'
        data_without_field = {'$unsetField': {'field': {'$literal': field_name}, 'input': '$$this.data'}}
        kept_items = {
            '$filter': {
                'input': f'${field_path}',
                'cond': {'$or': [{'$ne': [data_without_field, {}]}, {'$eq': ['$$this.data', {}]}]},
            }
        }
        items_without_field = {
            '$map': {'input': kept_items, 'in': {'$mergeObjects': ['$$this', {'data': data_without_field}]}}
        }

        await self.collection.update_many(
            filter={f'{field_path}.data.{field_name}': {'$exists': True}},
            update=[{'$set': {field_path: items_without_field, 'modified': utc_now()}}],
            session=session,
        )

    @staticmethod
    def build_extra_data_pipeline(
        *,
        query: dict[str, Any] | None = None,
        category_source: str,
        category_name: str,
        category_type: ExtraDataCategoryType,
        search_str: str | None = None,
        escape_search_str: bool = True,
        group_by_fields: list[str] | None = None,
        field_names: list[str] | None = None,
        sort: dict[str, SortOrder] | None = None,
        with_minion: bool = False,
    ) -> list[dict[str, Any]]:
        pipeline: list[dict[str, Any]] = []

        if query:
            pipeline.append({'$match': query})

        source_input = {
            '$filter': {
                'input': {'$objectToArray': {'$ifNull': ['$extra_static', {}]}},
                'as': 'src_pair',
                'cond': {'$eq': ['$$src_pair.k', category_source]},
            }
        }
        name_input = {
            '$filter': {
                'input': {'$objectToArray': '$$categories'},
                'as': 'cat_pair',
                'cond': {'$eq': ['$$cat_pair.k', category_name]},
            }
        }

        entry_meta = {
            '_id': {'$toString': '$minions._id'},
            'is_system': '$minions.is_system',
            'updated_at': '$minions.updated_at',
            '_source': '$source',
            '_name': '$name',
        }
        lookup_pipeline: list[dict[str, Any]] = [
            {'$match': {'source': category_source, 'name': category_name}},
            {'$unwind': '$minions'},
            {'$match': {'$expr': {'$eq': ['$minions.minion_id', '$$mid']}}},
            {'$replaceRoot': {'newRoot': {'$mergeObjects': ['$data', '$minions.data', entry_meta]}}},
        ]

        static_map = {
            '$map': {
                'input': '$$this.v',
                'as': 'it',
                'in': {
                    '$mergeObjects': [
                        '$$it.data',
                        {
                            '_id': {'$toString': '$$it._id'},
                            'is_system': '$$it.is_system',
                            'updated_at': '$$it.updated_at',
                            '_source': '$$src_name',
                            '_name': '$$this.k',
                        },
                    ]
                },
            }
        }
        inner_reduce = {
            '$reduce': {'input': name_input, 'initialValue': [], 'in': {'$concatArrays': ['$$value', static_map]}}
        }
        outer_reduce = {
            '$reduce': {
                'input': source_input,
                'initialValue': [],
                'in': {
                    '$let': {
                        'vars': {'src_name': '$$this.k', 'categories': '$$this.v'},
                        'in': {'$concatArrays': ['$$value', inner_reduce]},
                    }
                },
            }
        }

        skip_lookup = category_type == ExtraDataCategoryType.STATIC
        is_grouped = group_by_fields is not None
        minion_fields = {'_minion_id': '$minion_id', '_master': '$master'} if with_minion else {}

        if skip_lookup:
            pipeline.extend(
                [
                    {'$addFields': {'_static_items': outer_reduce}},
                    {'$project': {'_id': 1 if is_grouped else 0, **minion_fields, 'items': '$_static_items'}},
                    {'$unwind': '$items'},
                ]
            )
        else:
            pipeline.extend(
                [
                    {
                        '$lookup': {
                            'from': 'minion_extra_data',
                            'localField': '_id',
                            'foreignField': 'minions.minion_id',
                            'let': {'mid': '$_id'},
                            'pipeline': lookup_pipeline,
                            'as': '_aggregated_items',
                        }
                    },
                    {'$addFields': {'_static_items': outer_reduce}},
                    {
                        '$project': {
                            '_id': 1 if is_grouped else 0,
                            **minion_fields,
                            'items': {'$concatArrays': ['$_static_items', '$_aggregated_items']},
                        }
                    },
                    {'$unwind': '$items'},
                ]
            )

        if group_by_fields is not None:
            group_key: dict[str, Any] = {field: {'$ifNull': [f'$items.{field}', None]} for field in group_by_fields}
            group_key['_source'] = '$items._source'
            group_key['_name'] = '$items._name'

            pipeline.extend(
                [
                    {'$group': {'_id': group_key, '_minions': {'$addToSet': '$_id'}}},
                    {
                        '$replaceRoot': {
                            'newRoot': {'$mergeObjects': ['$_id', {'_minions_count': {'$size': '$_minions'}}]}
                        }
                    },
                ]
            )
        elif with_minion:
            pipeline.append(
                {
                    '$replaceRoot': {
                        'newRoot': {'$mergeObjects': ['$items', {'_minion_id': '$_minion_id', '_master': '$_master'}]}
                    }
                }
            )
        else:
            pipeline.extend(
                [
                    {'$replaceRoot': {'newRoot': '$items'}},
                    {'$group': {'_id': '$$ROOT'}},
                    {'$replaceRoot': {'newRoot': '$_id'}},
                ]
            )

        if search_str:
            pipeline.append(AnySearchAggregationStage(search=search_str, escape=escape_search_str).render_stage())

        if with_minion:
            return pipeline

        full_sort = {'_source': SortOrder.ASC, '_name': SortOrder.ASC, **(sort or {})}
        tiebreaker_fields = group_by_fields or field_names or []
        full_sort.update({field: SortOrder.ASC for field in tiebreaker_fields if field not in full_sort})

        pipeline.append({'$sort': full_sort})

        return pipeline

    async def get_extra_data_list_paginated(
        self,
        *,
        query: dict[str, Any] | None = None,
        category_source: str,
        category_name: str,
        category_type: ExtraDataCategoryType,
        search_str: str | None = None,
        escape_search_str: bool = True,
        group_by_fields: list[str] | None = None,
        field_names: list[str] | None = None,
        limit: int = 0,
        skip: int = 0,
        sort: dict[str, SortOrder] | None = None,
        session: MongoAsyncClientSession | None = None,
    ) -> tuple[int, list[dict[str, Any]]]:
        pipeline = self.build_extra_data_pipeline(
            query=query,
            category_source=category_source,
            category_name=category_name,
            category_type=category_type,
            search_str=search_str,
            escape_search_str=escape_search_str,
            group_by_fields=group_by_fields,
            field_names=field_names,
            sort=sort,
        )

        return await self.aggregate_paginated(pipeline, skip, limit, session=session)

    async def iter_extra_data(
        self,
        *,
        query: dict[str, Any] | None = None,
        category_source: str,
        category_name: str,
        category_type: ExtraDataCategoryType,
        search_str: str | None = None,
        escape_search_str: bool = True,
        group_by_fields: list[str] | None = None,
        field_names: list[str] | None = None,
        sort: dict[str, SortOrder] | None = None,
        with_minion: bool = False,
        session: MongoAsyncClientSession | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        pipeline = self.build_extra_data_pipeline(
            query=query,
            category_source=category_source,
            category_name=category_name,
            category_type=category_type,
            search_str=search_str,
            escape_search_str=escape_search_str,
            group_by_fields=group_by_fields,
            field_names=field_names,
            sort=sort,
            with_minion=with_minion,
        )

        async for row in self.aggregate_iter(pipeline, session=session):
            yield row

    class Meta:
        collection_name = 'minions'
        auto_now_add_fields: ClassVar[list[str]] = ['created']
        auto_now_fields: ClassVar[list[str]] = ['modified']
        query_overrides: ClassVar[dict[re.Pattern, str]] = {
            re.compile(r'^last_activity_seconds$'): 'last_activity_seconds_query_override',
            re.compile(r'^is_never_active$'): 'is_never_active_query_override',
            re.compile(r'^is_not_active$'): 'is_not_active_query_override',
            re.compile(r'^extra\.(?P<source>[^.]+)\.(?P<name>[^.]+)\.(?P<sub_field>.+)$'): 'extra_query_override',
            re.compile(r'^collection$'): 'collection_query_override',
        }
        collection_index_to_keys: ClassVar[dict[str, _IndexKeyHint]] = {
            'minion_id_master_unique_index_asc': [('minion_id', pymongo.ASCENDING), ('master', pymongo.ASCENDING)],
            'master_asc': [('master', pymongo.ASCENDING)],
            'created_asc': [('created', pymongo.ASCENDING)],
            'last_activity_asc': [('last_activity', pymongo.ASCENDING)],
            'grains_wildcard': [('grain.$**', pymongo.ASCENDING)],
            'extra_static_wildcard': [('extra_static.$**', pymongo.ASCENDING)],
        }
        aggregations: ClassVar[AggregationsStore] = AggregationsStore(
            aggregations=[
                AggregatedField(
                    field_name='is_never_active',
                    stages=[
                        AddFieldsAggregationStage(
                            fields={'is_never_active': {'$eq': [{'$ifNull': ['$last_activity', None]}, None]}}
                        )
                    ],
                ),
                AggregatedField(field_name='is_not_active', stages=[IsNotActiveAggregationStage()]),
                AggregatedField(
                    field_name='extra_aggregated',
                    stages=[
                        LookupAggregationStage(
                            from_collection='minion_extra_data',
                            local_field='_id',
                            foreign_field='minions.minion_id',
                            let={'minion_id': '$_id'},
                            pipeline=[
                                UnwindAggregationStage(path='$minions'),
                                MatchAggregationStage(query={'$expr': {'$eq': ['$minions.minion_id', '$$minion_id']}}),
                                AddFieldsAggregationStage(
                                    fields={'_merged_value': {'$mergeObjects': ['$data', '$minions.data']}}
                                ),
                                GroupAggregationStage(
                                    group_id={'source': '$source', 'name': '$name'},
                                    fields={
                                        'values': {'$push': '$_merged_value'},
                                    },
                                ),
                                GroupAggregationStage(
                                    group_id='$_id.source',
                                    fields={
                                        'names': {'$push': {'k': '$_id.name', 'v': '$values'}},
                                    },
                                ),
                                ProjectAggregationStage(
                                    fields={'_id': 0, 'k': '$_id', 'v': {'$arrayToObject': '$names'}}
                                ),
                            ],
                            as_field='_extra_grouped',
                        ),
                        AddFieldsAggregationStage(fields={'extra_aggregated': {'$arrayToObject': '$_extra_grouped'}}),
                        UnsetAggregationStage(fields=['_extra_grouped']),
                    ],
                ),
                AggregatedField(
                    field_name='extra',
                    stages=[
                        AddFieldsAggregationStage(
                            fields={
                                'extra': {
                                    '$arrayToObject': {
                                        '$reduce': {
                                            'input': {
                                                '$concatArrays': [
                                                    EXTRA_STATIC_DATA_AS_KV,
                                                    {'$objectToArray': '$extra_aggregated'},
                                                ]
                                            },
                                            'initialValue': [],
                                            'in': {
                                                '$let': {
                                                    'vars': {'idx': {'$indexOfArray': ['$$value.k', '$$this.k']}},
                                                    'in': {
                                                        '$cond': [
                                                            {'$eq': ['$$idx', -1]},
                                                            {'$concatArrays': ['$$value', ['$$this']]},
                                                            {
                                                                '$concatArrays': [
                                                                    {'$slice': ['$$value', '$$idx']},
                                                                    [
                                                                        {
                                                                            'k': '$$this.k',
                                                                            'v': {
                                                                                '$mergeObjects': [
                                                                                    {
                                                                                        '$arrayElemAt': [
                                                                                            '$$value.v',
                                                                                            '$$idx',
                                                                                        ]
                                                                                    },
                                                                                    '$$this.v',
                                                                                ]
                                                                            },
                                                                        }
                                                                    ],
                                                                    {
                                                                        '$slice': [
                                                                            '$$value',
                                                                            {'$add': ['$$idx', 1]},
                                                                            {'$size': '$$value'},
                                                                        ]
                                                                    },
                                                                ]
                                                            },
                                                        ]
                                                    },
                                                }
                                            },
                                        }
                                    }
                                }
                            }
                        )
                    ],
                    parent_aggregations=['extra_aggregated'],
                ),
            ],
        )


def get_minion_repository(
    db: Annotated[AsyncDatabase, Depends(get_mongo)],
    extra_data_repository: Annotated[ExtraDataRepository, Depends(get_extra_data_repository)],
    collection_repository: Annotated[CollectionRepository, Depends(get_collection_repository)],
) -> MinionRepository:
    return MinionRepository(
        database=db, extra_data_repository=extra_data_repository, collection_repository=collection_repository
    )
