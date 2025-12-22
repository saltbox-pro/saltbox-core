from typing import Annotated, Any, ClassVar

from fastapi import Depends
from pymongo.asynchronous.database import AsyncDatabase

from saltbox_core.tasks.schemas.task import TaskModel
from saltbox_sdk.db.mongo.config import get_mongo
from saltbox_sdk.db.mongo.repository_base import BaseMongoRepository


class TaskRepository(BaseMongoRepository[TaskModel]):
    class Meta:
        collection_name = 'tasks'
        auto_now_add_fields: ClassVar[list[str]] = ['created']
        auto_now_fields: ClassVar[list[str]] = ['modified']
        joins: ClassVar[dict[str, list[Any]]] = {
            'target_collection': [
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
            'task_template': [
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
            'status': [
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
        }


def get_task_repository(db: Annotated[AsyncDatabase, Depends(get_mongo)]) -> TaskRepository:
    return TaskRepository(db)
