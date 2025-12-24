from typing import Annotated, ClassVar

from fastapi import Depends
from pymongo.asynchronous.database import AsyncDatabase

from saltbox_core.tasks.schemas.tasks_minion import TaskMinionModel
from saltbox_sdk.db.mongo.config import get_mongo
from saltbox_sdk.db.mongo.repository_base import BaseMongoRepository
from saltbox_sdk.db.mongo.utils import AggregatedField, AggregationsStore


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
                        {
                            '$lookup': {
                                'from': 'minions',
                                'localField': 'minion_inner_id',
                                'foreignField': '_id',
                                'as': 'minion',
                            }
                        },
                        {'$unwind': '$minion'},
                    ],
                ),
                AggregatedField(
                    field_name='minion_id',
                    stages=[{'$addFields': {'minion_id': '$minion.minion_id'}}],
                    parent_aggregations=['minion'],
                ),
                AggregatedField(
                    field_name='master',
                    stages=[{'$addFields': {'master': '$minion.master'}}],
                    parent_aggregations=['minion'],
                ),
                AggregatedField(
                    field_name='last_activity',
                    stages=[{'$addFields': {'last_activity': '$minion.last_activity'}}],
                    parent_aggregations=['minion'],
                ),
            ]
        )


def get_task_minion_repository(db: Annotated[AsyncDatabase, Depends(get_mongo)]) -> TaskMinionRepository:
    return TaskMinionRepository(db)
