from typing import Annotated, Any, ClassVar

import pymongo
from fastapi import Depends
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.operations import _IndexKeyHint

from saltbox_core.masters.schemas.master_schemas import MasterModel
from saltbox_core.minion_collections.utils.activity_filter import get_never_active_condition, get_not_active_condition
from saltbox_sdk.db.mongo.aggregations import (
    AbstractAggregationStage,
    AddFieldsAggregationStage,
    AggregatedField,
    AggregationsStore,
    LookupAggregationStage,
    UnwindAggregationStage,
)
from saltbox_sdk.db.mongo.config import get_mongo
from saltbox_sdk.db.mongo.repository_base import BaseMongoRepository


class MinionsActivityGroupStage(AbstractAggregationStage):
    def render_stage(self) -> dict[str, Any]:
        return {
            '$group': {
                '_id': None,
                'total': {'$sum': 1},
                'never_active': {'$sum': {'$cond': [get_never_active_condition(), 1, 0]}},
                'not_active': {'$sum': {'$cond': [get_not_active_condition(), 1, 0]}},
            }
        }


MINIONS_STATS_STAGES: list[AbstractAggregationStage] = [
    LookupAggregationStage(
        from_collection='minions',
        local_field='master_id',
        foreign_field='master',
        as_field='minions_stats',
        pipeline=[MinionsActivityGroupStage()],
    ),
    UnwindAggregationStage(path='$minions_stats', preserve_null_and_empty_arrays=True),
]


class MasterRepository(BaseMongoRepository[MasterModel]):
    class Meta:
        collection_name = 'master'
        auto_now_add_fields: ClassVar[list[str]] = ['created']
        auto_now_fields: ClassVar[list[str]] = ['modified']
        collection_index_to_keys: ClassVar[dict[str, _IndexKeyHint]] = {
            'master_id_unique_index_asc': [('master_id', pymongo.ASCENDING)],
            'status_asc': [('status', pymongo.ASCENDING)],
        }
        aggregations: ClassVar[AggregationsStore] = AggregationsStore(
            aggregations=[
                AggregatedField(
                    field_name='minions_count',
                    stages=[
                        *MINIONS_STATS_STAGES,
                        AddFieldsAggregationStage(fields={'minions_count': {'$ifNull': ['$minions_stats.total', 0]}}),
                    ],
                ),
                AggregatedField(
                    field_name='never_active_minions_count',
                    stages=[
                        *MINIONS_STATS_STAGES,
                        AddFieldsAggregationStage(
                            fields={'never_active_minions_count': {'$ifNull': ['$minions_stats.never_active', 0]}}
                        ),
                    ],
                ),
                AggregatedField(
                    field_name='not_active_minions_count',
                    stages=[
                        *MINIONS_STATS_STAGES,
                        AddFieldsAggregationStage(
                            fields={'not_active_minions_count': {'$ifNull': ['$minions_stats.not_active', 0]}}
                        ),
                    ],
                ),
            ]
        )

    async def get_by_master_id(self, value: str) -> MasterModel:
        return await self.get(query={'master_id': value})


def get_master_repository(db: Annotated[AsyncDatabase, Depends(get_mongo)]) -> MasterRepository:
    return MasterRepository(db)
