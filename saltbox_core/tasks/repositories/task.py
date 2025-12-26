from typing import Annotated, ClassVar

from fastapi import Depends
from pymongo.asynchronous.database import AsyncDatabase

from saltbox_core.tasks.schemas.task import TaskModel
from saltbox_sdk.db.mongo.aggregations import (
    AddFieldsAggregationStage,
    AggregatedField,
    AggregationsStore,
    LookupAggregationStage,
    UnwindAggregationStage,
)
from saltbox_sdk.db.mongo.config import get_mongo
from saltbox_sdk.db.mongo.repository_base import BaseMongoRepository


class TaskRepository(BaseMongoRepository[TaskModel]):
    class Meta:
        collection_name = 'tasks'
        auto_now_add_fields: ClassVar[list[str]] = ['created']
        auto_now_fields: ClassVar[list[str]] = ['modified']
        aggregations: ClassVar[AggregationsStore] = AggregationsStore(
            aggregations=[
                AggregatedField(
                    field_name='target_collection',
                    stages=[
                        LookupAggregationStage(
                            from_collection='minion_collections',
                            local_field='target_collection_id',
                            foreign_field='_id',
                            as_field='target_collection',
                        ),
                        UnwindAggregationStage(path='$target_collection', preserve_null_and_empty_arrays=True),
                    ],
                ),
                AggregatedField(
                    field_name='task_template',
                    stages=[
                        LookupAggregationStage(
                            from_collection='task_templates',
                            local_field='task_template_id',
                            foreign_field='_id',
                            as_field='task_template',
                        ),
                        UnwindAggregationStage(path='$task_template', preserve_null_and_empty_arrays=True),
                    ],
                ),
                AggregatedField(
                    field_name='status',
                    stages=[
                        LookupAggregationStage(
                            from_collection='task_statuses',
                            local_field='_id',
                            foreign_field='task_id',
                            as_field='status',
                            pipeline=[{'$sort': {'created': -1}}, {'$limit': 1}],
                        ),
                        UnwindAggregationStage(path='$status', preserve_null_and_empty_arrays=True),
                    ],
                ),
                AggregatedField(
                    field_name='minions_count',
                    stages=[
                        LookupAggregationStage(
                            from_collection='task_minions',
                            local_field='_id',
                            foreign_field='task_id',
                            as_field='minions_count.total',
                            pipeline=[{'$count': 'count'}],
                        ),
                        LookupAggregationStage(
                            from_collection='task_minions',
                            local_field='_id',
                            foreign_field='task_id',
                            as_field='minions_count.pending',
                            pipeline=[{'$match': {'status': 'pending'}}, {'$count': 'count'}],
                        ),
                        LookupAggregationStage(
                            from_collection='task_minions',
                            local_field='_id',
                            foreign_field='task_id',
                            as_field='minions_count.busy',
                            pipeline=[{'$match': {'status': 'busy'}}, {'$count': 'count'}],
                        ),
                        LookupAggregationStage(
                            from_collection='task_minions',
                            local_field='_id',
                            foreign_field='task_id',
                            as_field='minions_count.in_work',
                            pipeline=[{'$match': {'status': 'in_work'}}, {'$count': 'count'}],
                        ),
                        LookupAggregationStage(
                            from_collection='task_minions',
                            local_field='_id',
                            foreign_field='task_id',
                            as_field='minions_count.success',
                            pipeline=[{'$match': {'status': 'success'}}, {'$count': 'count'}],
                        ),
                        LookupAggregationStage(
                            from_collection='task_minions',
                            local_field='_id',
                            foreign_field='task_id',
                            as_field='minions_count.failed',
                            pipeline=[{'$match': {'status': 'failed'}}, {'$count': 'count'}],
                        ),
                        UnwindAggregationStage(path='$minions_count.total', preserve_null_and_empty_arrays=True),
                        UnwindAggregationStage(path='$minions_count.pending', preserve_null_and_empty_arrays=True),
                        UnwindAggregationStage(path='$minions_count.busy', preserve_null_and_empty_arrays=True),
                        UnwindAggregationStage(path='$minions_count.in_work', preserve_null_and_empty_arrays=True),
                        UnwindAggregationStage(path='$minions_count.success', preserve_null_and_empty_arrays=True),
                        UnwindAggregationStage(path='$minions_count.failed', preserve_null_and_empty_arrays=True),
                        AddFieldsAggregationStage(
                            fields={
                                'minions_count.total': {'$ifNull': ['$minions_count.total.count', 0]},
                                'minions_count.pending': {'$ifNull': ['$minions_count.pending.count', 0]},
                                'minions_count.busy': {'$ifNull': ['$minions_count.busy.count', 0]},
                                'minions_count.in_work': {'$ifNull': ['$minions_count.in_work.count', 0]},
                                'minions_count.success': {'$ifNull': ['$minions_count.success.count', 0]},
                                'minions_count.failed': {'$ifNull': ['$minions_count.failed.count', 0]},
                            }
                        ),
                    ],
                ),
            ]
        )


def get_task_repository(db: Annotated[AsyncDatabase, Depends(get_mongo)]) -> TaskRepository:
    return TaskRepository(db)
