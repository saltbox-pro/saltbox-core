from typing import Annotated, ClassVar

import pymongo
from fastapi import Depends
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.operations import _IndexKeyHint

from saltbox_core.pillars.schemas import PillarTgtType
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
        collection_index_to_keys: ClassVar[dict[str, _IndexKeyHint]] = {
            'source_asc': [('source.type', pymongo.ASCENDING), ('source.id', pymongo.ASCENDING)],
            'task_type_asc': [('task_type', pymongo.ASCENDING)],
        }
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
                            from_collection='task_tpls',
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
                AggregatedField(
                    field_name='pillars',
                    stages=[
                        LookupAggregationStage(
                            from_collection='pillars',
                            let={'task_id': '$_id'},
                            pipeline=[
                                {
                                    '$match': {
                                        '$expr': {
                                            '$and': [
                                                {'$eq': ['$tgt_id', '$$task_id']},
                                                {'$eq': ['$tgt_type', PillarTgtType.TASK.value]},
                                            ]
                                        }
                                    }
                                },
                                {
                                    '$project': {
                                        '_id': 0,
                                        'name': 1,
                                        'value': {
                                            '$cond': [
                                                {'$eq': ['$is_secret', True]},
                                                '*******',
                                                '$value',
                                            ]
                                        },
                                    }
                                },
                            ],
                            as_field='pillars',
                        ),
                        AddFieldsAggregationStage(
                            fields={
                                'pillars': {
                                    '$arrayToObject': {
                                        '$map': {
                                            'input': {'$ifNull': ['$pillars', []]},
                                            'as': 'pillar',
                                            'in': {'k': '$$pillar.name', 'v': '$$pillar.value'},
                                        }
                                    }
                                }
                            }
                        ),
                    ],
                ),
            ]
        )


def get_task_repository(db: Annotated[AsyncDatabase, Depends(get_mongo)]) -> TaskRepository:
    return TaskRepository(db)
