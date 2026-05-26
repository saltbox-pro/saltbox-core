import re
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, ClassVar, cast, overload

import pymongo
from fastapi import Depends
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.operations import _IndexKeyHint

# from saltbox_core.config import logger
from saltbox_core.minion_collections.schemas.minion import MinionModel
from saltbox_sdk.db.mongo.aggregations import (
    AbstractAggregationStage,
    AddFieldsAggregationStage,
    AggregatedField,
    AggregationsStore,
    LookupAggregationStage,
    MatchAggregationStage,
)
from saltbox_sdk.db.mongo.config import get_mongo
from saltbox_sdk.db.mongo.repository_base import BaseMongoRepository, ProjectionModel
from saltbox_sdk.db.mongo.schemas_base import SortOrder

EXTRA_DATA_FIELD_NAME_REGEXP = re.compile(
    r'^extra\.(?P<category_source>[^.]+)\.(?P<category_name>[^.]+)\.(?P<field>.+)$'
)


def build_minion_aggregations_store(query_by_extra_data: dict | None = None) -> AggregationsStore:
    lookup_extra_grouped_pipline: list[AbstractAggregationStage | dict] = [
        MatchAggregationStage(query={'$expr': {'$in': ['$_id', '$$extra_ids']}}),
    ]

    if query_by_extra_data:
        lookup_extra_grouped_pipline.append(MatchAggregationStage(query=query_by_extra_data))

    lookup_extra_grouped_pipline.extend(
        [
            {
                '$group': {
                    '_id': {'source': '$source', 'name': '$name'},
                    'values': {'$push': '$value'},
                }
            },
            {
                '$group': {
                    '_id': '$_id.source',
                    'names': {'$push': {'k': '$_id.name', 'v': '$values'}},
                }
            },
            {'$project': {'_id': 0, 'k': '$_id', 'v': {'$arrayToObject': '$names'}}},
        ]
    )
    extra_data_aggregated_field_stages: list[AbstractAggregationStage] = [
        LookupAggregationStage(
            from_collection='minion_extra_data_item',
            let={'extra_ids': {'$ifNull': ['$_extra', []]}},
            pipeline=lookup_extra_grouped_pipline,
            as_field='_extra_grouped',
        ),
        AddFieldsAggregationStage(fields={'extra': {'$arrayToObject': '$_extra_grouped'}}),
    ]

    if query_by_extra_data:
        extra_data_aggregated_field_stages.append(MatchAggregationStage(query={'extra': {'$ne': {}}}))

    extra_data_aggregated_field = AggregatedField(
        field_name='extra',
        stages=extra_data_aggregated_field_stages,
    )

    return AggregationsStore(
        aggregations=[extra_data_aggregated_field],
    )


class MinionRepository(BaseMongoRepository[MinionModel]):
    def last_activity_seconds_query_override(self, field_name: str, field_value: Any) -> tuple[str, Any]:
        if field_name != 'last_activity_seconds':
            return field_name, field_value

        if isinstance(field_value, dict):
            lookup = cast(str, next(iter(field_value)))
            value = field_value[lookup]

            if lookup in ['$in', '$nin']:
                return 'last_activity', {
                    lookup: [datetime.now(UTC) - timedelta(seconds=float(item_val)) for item_val in value]
                }
            else:
                lookup = {'$lt': '$gt', '$lte': '$gte', '$gt': '$lt', '$gte': '$lte'}.get(lookup, lookup)
                return 'last_activity', {lookup: datetime.now(UTC) - timedelta(seconds=float(value))}
        else:
            return 'last_activity', datetime.now(UTC) - timedelta(seconds=float(field_value))

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

    async def prepare_aggregation_pipeline(
        self,
        projection: dict[str, Any],
        query: dict[str, Any] | None = None,
        limit: int | None = None,
        skip: int | None = None,
        sort: dict[str, SortOrder] | None = None,
    ) -> list[dict]:
        fields_names = list(projection.keys())

        if query:
            extra_query_list: list[dict[str, Any]] = []

            for field in self._extract_fields_from_query(query):
                field_name, field_value = field
                fields_names.append(field_name)
                extra_field_name_match = EXTRA_DATA_FIELD_NAME_REGEXP.match(field_name)

                if extra_field_name_match:
                    extra_query_list.append(
                        {
                            'source': extra_field_name_match.group('category_source'),
                            'name': extra_field_name_match.group('category_name'),
                            f'value.{extra_field_name_match.group("field")}': field_value,
                        }
                    )

            if extra_query_list:
                return build_minion_aggregations_store(query_by_extra_data={'$or': extra_query_list}).build_pipeline(
                    fields_names=fields_names
                )

        return self.aggregations.build_pipeline(fields_names=fields_names)

    class Meta:
        collection_name = 'minions'
        auto_now_add_fields: ClassVar[list[str]] = ['created']
        auto_now_fields: ClassVar[list[str]] = ['modified']
        query_overrides: ClassVar[dict[str, str]] = {'last_activity_seconds': 'last_activity_seconds_query_override'}
        collection_index_to_keys: ClassVar[dict[str, _IndexKeyHint]] = {
            'minion_id_master_unique_index_asc': [('minion_id', pymongo.ASCENDING), ('master', pymongo.ASCENDING)],
            'created_asc': [('created', pymongo.ASCENDING)],
            'last_activity_asc': [('last_activity', pymongo.ASCENDING)],
            'grains_text': [('grains', pymongo.TEXT)],
        }
        aggregations: ClassVar[AggregationsStore] = build_minion_aggregations_store()


def get_minion_repository(db: Annotated[AsyncDatabase, Depends(get_mongo)]) -> MinionRepository:
    return MinionRepository(db)
