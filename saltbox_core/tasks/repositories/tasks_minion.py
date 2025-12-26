from typing import Annotated, ClassVar

from fastapi import Depends
from pymongo.asynchronous.database import AsyncDatabase

from saltbox_core.tasks.schemas.tasks_minion import TaskMinionModel
from saltbox_sdk.db.mongo.aggregations import (
    AddFieldsAggregationStage,
    AggregatedField,
    AggregationsStore,
    LookupAggregationStage,
    UnwindAggregationStage,
)
from saltbox_sdk.db.mongo.config import get_mongo
from saltbox_sdk.db.mongo.repository_base import BaseMongoRepository


class TaskMinionRepository(BaseMongoRepository[TaskMinionModel]):
    class Meta:
        collection_name = 'task_minions'
        auto_now_add_fields: ClassVar[list[str]] = ['created']
        auto_now_fields: ClassVar[list[str]] = ['modified']
        aggregations: ClassVar[AggregationsStore] = AggregationsStore(
            aggregations=[
                AggregatedField(
                    field_name='minion',
                    stages=[
                        LookupAggregationStage(
                            from_collection='minions',
                            local_field='minion_inner_id',
                            foreign_field='_id',
                            as_field='minion',
                        ),
                        UnwindAggregationStage(path='$minion'),
                    ],
                ),
                AggregatedField(
                    field_name='minion_id',
                    stages=[AddFieldsAggregationStage(fields={'minion_id': '$minion.minion_id'})],
                    parent_aggregations=['minion'],
                ),
                AggregatedField(
                    field_name='master',
                    stages=[AddFieldsAggregationStage(fields={'master': '$minion.master'})],
                    parent_aggregations=['minion'],
                ),
                AggregatedField(
                    field_name='last_activity',
                    stages=[AddFieldsAggregationStage(fields={'last_activity': '$minion.last_activity'})],
                    parent_aggregations=['minion'],
                ),
            ]
        )


def get_task_minion_repository(db: Annotated[AsyncDatabase, Depends(get_mongo)]) -> TaskMinionRepository:
    return TaskMinionRepository(db)
