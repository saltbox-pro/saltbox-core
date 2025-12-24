from typing import Annotated, ClassVar

from fastapi import Depends
from pymongo.asynchronous.database import AsyncDatabase

from saltbox_core.tasks.schemas.task import TaskModel
from saltbox_sdk.db.mongo.config import get_mongo
from saltbox_sdk.db.mongo.repository_base import BaseMongoRepository
from saltbox_sdk.db.mongo.utils import AggregatedField, AggregationsStore


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
                        {
                            '$lookup': {
                                'from': 'minion_collections',
                                'localField': 'target_collection_id',
                                'foreignField': '_id',
                                'as': 'target_collection',
                            }
                        },
                        {'$unwind': '$target_collection'},
                    ],
                ),
                AggregatedField(
                    field_name='task_template',
                    stages=[
                        {
                            '$lookup': {
                                'from': 'task_templates',
                                'localField': 'task_template_id',
                                'foreignField': '_id',
                                'as': 'task_template',
                            }
                        },
                        {'$unwind': {'path': '$task_template', 'preserveNullAndEmptyArrays': True}},
                    ],
                ),
                AggregatedField(
                    field_name='status',
                    stages=[
                        {
                            '$lookup': {
                                'from': 'task_statuses',
                                'localField': '_id',
                                'foreignField': 'task_id',
                                'as': 'status',
                                'pipeline': [{'$sort': {'created': -1}}, {'$limit': 1}],
                            }
                        },
                        {'$unwind': {'path': '$status', 'preserveNullAndEmptyArrays': True}},
                    ],
                ),
                AggregatedField(
                    field_name='minions_count',
                    stages=[
                        {
                            '$lookup': {
                                'from': 'task_minions',
                                'localField': '_id',
                                'foreignField': 'task_id',
                                'as': 'minions_count.total',
                                'pipeline': [{'$count': 'count'}],
                            }
                        },
                        {
                            '$lookup': {
                                'from': 'task_minions',
                                'localField': '_id',
                                'foreignField': 'task_id',
                                'as': 'minions_count.pending',
                                'pipeline': [{'$match': {'status': 'pending'}}, {'$count': 'count'}],
                            }
                        },
                        {
                            '$lookup': {
                                'from': 'task_minions',
                                'localField': '_id',
                                'foreignField': 'task_id',
                                'as': 'minions_count.busy',
                                'pipeline': [{'$match': {'status': 'busy'}}, {'$count': 'count'}],
                            }
                        },
                        {
                            '$lookup': {
                                'from': 'task_minions',
                                'localField': '_id',
                                'foreignField': 'task_id',
                                'as': 'minions_count.in_work',
                                'pipeline': [{'$match': {'status': 'in_work'}}, {'$count': 'count'}],
                            }
                        },
                        {
                            '$lookup': {
                                'from': 'task_minions',
                                'localField': '_id',
                                'foreignField': 'task_id',
                                'as': 'minions_count.success',
                                'pipeline': [{'$match': {'status': 'success'}}, {'$count': 'count'}],
                            }
                        },
                        {
                            '$lookup': {
                                'from': 'task_minions',
                                'localField': '_id',
                                'foreignField': 'task_id',
                                'as': 'minions_count.failed',
                                'pipeline': [{'$match': {'status': 'failed'}}, {'$count': 'count'}],
                            }
                        },
                        {'$unwind': {'path': '$minions_count.total', 'preserveNullAndEmptyArrays': True}},
                        {'$unwind': {'path': '$minions_count.pending', 'preserveNullAndEmptyArrays': True}},
                        {'$unwind': {'path': '$minions_count.busy', 'preserveNullAndEmptyArrays': True}},
                        {'$unwind': {'path': '$minions_count.in_work', 'preserveNullAndEmptyArrays': True}},
                        {'$unwind': {'path': '$minions_count.success', 'preserveNullAndEmptyArrays': True}},
                        {'$unwind': {'path': '$minions_count.failed', 'preserveNullAndEmptyArrays': True}},
                        {
                            '$addFields': {
                                'minions_count.total': {'$ifNull': ['$minions_count.total.count', 0]},
                                'minions_count.pending': {'$ifNull': ['$minions_count.pending.count', 0]},
                                'minions_count.busy': {'$ifNull': ['$minions_count.busy.count', 0]},
                                'minions_count.in_work': {'$ifNull': ['$minions_count.in_work.count', 0]},
                                'minions_count.success': {'$ifNull': ['$minions_count.success.count', 0]},
                                'minions_count.failed': {'$ifNull': ['$minions_count.failed.count', 0]},
                            }
                        },
                    ],
                ),
            ]
        )


def get_task_repository(db: Annotated[AsyncDatabase, Depends(get_mongo)]) -> TaskRepository:
    return TaskRepository(db)
