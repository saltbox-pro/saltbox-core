import re
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, ClassVar, cast, overload

import pymongo
from fastapi import Depends
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.asynchronous.database import AsyncDatabase as MongoAsyncDatabase
from pymongo.operations import _IndexKeyHint

from saltbox_core.minion_collections.repositories.extra_data import ExtraDataRepository, get_extra_data_repository
from saltbox_core.minion_collections.schemas.minion import MinionModel
from saltbox_sdk.db.mongo.aggregations import (
    AddFieldsAggregationStage,
    AggregatedField,
    AggregationsStore,
    GroupAggregationStage,
    LookupAggregationStage,
    MatchAggregationStage,
    ProjectAggregationStage,
    UnsetAggregationStage,
)
from saltbox_sdk.db.mongo.config import get_mongo
from saltbox_sdk.db.mongo.repository_base import BaseMongoRepository, ProjectionModel
from saltbox_sdk.event_bus.schemas import ExtraDataCategoryType


class MinionRepository(BaseMongoRepository[MinionModel]):
    def __init__(
        self, database: MongoAsyncDatabase[Any], extra_data_repository: ExtraDataRepository, **kwargs: Any
    ) -> None:
        super().__init__(database=database)
        self.extra_data_repository = extra_data_repository

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

    async def extra_static_query_override(
        self, field_name: str, field_match: re.Match, field_value: Any, full_raw_query: dict
    ) -> dict[str, Any]:
        source: str = field_match.group('source')
        name: str = field_match.group('name')
        sub_field: str = field_match.group('sub_field')

        return {f'extra_static.{source}.{name}.{sub_field}': field_value}

    async def extra_aggregated_query_override(
        self, field_name: str, field_match: re.Match, field_value: Any, full_raw_query: dict
    ) -> dict[str, Any]:
        source: str = field_match.group('source')
        name: str = field_match.group('name')
        sub_field: str = field_match.group('sub_field')

        minion_ids = await self.extra_data_repository.get_minion_ids_by_filter(
            source=source, name=name, query={sub_field: field_value}
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

    class Meta:
        collection_name = 'minions'
        auto_now_add_fields: ClassVar[list[str]] = ['created']
        auto_now_fields: ClassVar[list[str]] = ['modified']
        query_overrides: ClassVar[dict[re.Pattern, str]] = {
            re.compile(r'^last_activity_seconds$'): 'last_activity_seconds_query_override',
            re.compile(
                r'^extra\.static\.(?P<source>[^.]+)\.(?P<name>[^.]+)\.(?P<sub_field>.+)'
            ): 'extra_static_query_override',
            re.compile(
                r'^extra\.aggregated\.(?P<source>[^.]+)\.(?P<name>[^.]+)\.(?P<sub_field>.+)$'
            ): 'extra_aggregated_query_override',
            re.compile(r'^extra\.(?P<source>[^.]+)\.(?P<name>[^.]+)\.(?P<sub_field>.+)$'): 'extra_query_override',
        }
        collection_index_to_keys: ClassVar[dict[str, _IndexKeyHint]] = {
            'minion_id_master_unique_index_asc': [('minion_id', pymongo.ASCENDING), ('master', pymongo.ASCENDING)],
            'created_asc': [('created', pymongo.ASCENDING)],
            'last_activity_asc': [('last_activity', pymongo.ASCENDING)],
            'grains_wildcard': [('grain.$**', pymongo.ASCENDING)],
            'extra_static_wildcard': [('extra_static.$**', pymongo.ASCENDING)],
        }
        aggregations: ClassVar[AggregationsStore] = AggregationsStore(
            aggregations=[
                AggregatedField(
                    field_name='extra_aggregated',
                    stages=[
                        LookupAggregationStage(
                            from_collection='minion_extra_data',
                            let={'minion_id': '$_id'},
                            pipeline=[
                                MatchAggregationStage(query={'$expr': {'$in': ['$$minion_id', '$minions.minion_id']}}),
                                AddFieldsAggregationStage(
                                    fields={
                                        '_minion_entry': {
                                            '$first': {
                                                '$filter': {
                                                    'input': '$minions',
                                                    'as': 'm',
                                                    'cond': {'$eq': ['$$m.minion_id', '$$minion_id']},
                                                }
                                            }
                                        }
                                    }
                                ),
                                AddFieldsAggregationStage(
                                    fields={'_merged_value': {'$mergeObjects': ['$data', '$_minion_entry.data']}}
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
                                                    {'$objectToArray': {'$ifNull': ['$extra_static', {}]}},
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
) -> MinionRepository:
    return MinionRepository(database=db, extra_data_repository=extra_data_repository)
