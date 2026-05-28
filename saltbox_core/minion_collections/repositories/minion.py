import re
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, ClassVar, cast, overload

import pymongo
from fastapi import Depends
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.operations import _IndexKeyHint

from saltbox_core.minion_collections.schemas.minion import MinionModel
from saltbox_sdk.db.mongo.aggregations import (
    AddFieldsAggregationStage,
    AggregatedField,
    AggregationsStore,
    LookupAggregationStage,
    MatchAggregationStage,
)
from saltbox_sdk.db.mongo.config import get_mongo
from saltbox_sdk.db.mongo.repository_base import BaseMongoRepository, ProjectionModel
from saltbox_sdk.db.mongo.schemas_base import PyObjectId


class MinionRepository(BaseMongoRepository[MinionModel]):
    def last_activity_seconds_query_override(
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

    def extra_static_query_override(
        self, field_name: str, field_match: re.Match, field_value: Any, full_raw_query: dict
    ) -> dict[str, Any]:
        return {f'extra_static.{field_match.group("sub_field")}': field_value}

    def extra_aggregated_query_override(
        self, field_name: str, field_match: re.Match, field_value: Any, full_raw_query: dict
    ) -> dict[str, Any]:
        return {}  # TODO (i.moshkov): Add filtering by aggregated extra data

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

    def __prepare_query__(self, query: PyObjectId | dict[str, Any] | None) -> dict[str, Any]:
        prepared_query = super().__prepare_query__(query=query)

        return prepared_query

    class Meta:
        collection_name = 'minions'
        auto_now_add_fields: ClassVar[list[str]] = ['created']
        auto_now_fields: ClassVar[list[str]] = ['modified']
        query_overrides: ClassVar[dict[re.Pattern, str]] = {
            re.compile(r'^last_activity_seconds$'): 'last_activity_seconds_query_override',
            re.compile(r'^extra\.static\.(?P<sub_field>.+)$'): 'extra_static_query_override',
            re.compile(r'^extra\.aggregated\.(?P<sub_field>.+)$'): 'extra_aggregated_query_override',
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
                            let={'minion_id_str': {'$toString': '$_id'}},
                            pipeline=[
                                AddFieldsAggregationStage(
                                    fields={
                                        '_minion_entry': {
                                            '$first': {
                                                '$filter': {
                                                    'input': {'$objectToArray': '$minions'},
                                                    'as': 'm',
                                                    'cond': {'$eq': ['$$m.k', '$$minion_id_str']},
                                                }
                                            }
                                        }
                                    }
                                ),
                                MatchAggregationStage(query={'$expr': {'$ne': ['$_minion_entry', None]}}),
                                AddFieldsAggregationStage(
                                    fields={'_merged_value': {'$mergeObjects': ['$data', '$_minion_entry.v']}}
                                ),
                                {
                                    '$group': {
                                        '_id': {'source': '$source', 'name': '$name'},
                                        'values': {'$push': '$_merged_value'},
                                    }
                                },
                                {
                                    '$group': {
                                        '_id': '$_id.source',
                                        'names': {'$push': {'k': '$_id.name', 'v': '$values'}},
                                    }
                                },
                                {'$project': {'_id': 0, 'k': '$_id', 'v': {'$arrayToObject': '$names'}}},
                            ],
                            as_field='_extra_grouped',
                        ),
                        AddFieldsAggregationStage(fields={'extra_aggregated': {'$arrayToObject': '$_extra_grouped'}}),
                    ],
                ),
                AggregatedField(
                    field_name='extra',
                    stages=[
                        AddFieldsAggregationStage(
                            fields={
                                'extra.aggregated': '$extra_aggregated',
                                'extra.static': {'$ifNull': ['$extra_static', {}]},
                            }
                        )
                    ],
                    parent_aggregations=['extra_aggregated'],
                ),
            ],
        )


def get_minion_repository(db: Annotated[AsyncDatabase, Depends(get_mongo)]) -> MinionRepository:
    return MinionRepository(db)
