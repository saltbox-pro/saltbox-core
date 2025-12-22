from typing import Annotated, Any, ClassVar

from fastapi import Depends
from pymongo.asynchronous.database import AsyncDatabase

from saltbox_core.tasks.schemas.tasks_minion import TaskMinionModel
from saltbox_sdk.db.mongo.config import get_mongo
from saltbox_sdk.db.mongo.repository_base import BaseMongoRepository


class TaskMinionRepository(BaseMongoRepository[TaskMinionModel]):
    class Meta:
        collection_name = 'task_minions'
        auto_now_add_fields: ClassVar[list[str]] = ['created']
        auto_now_fields: ClassVar[list[str]] = ['modified']
        joins: ClassVar[dict[str, list[Any]]] = {
            'minion_data': [
                {
                    '$lookup': {
                        'from': 'minions',
                        'localField': 'minion_inner_id',
                        'foreignField': '_id',
                        'as': 'minion_data',
                    }
                },
                {'$unwind': '$minion_data'},
            ],
        }


def get_task_minion_repository(db: Annotated[AsyncDatabase, Depends(get_mongo)]) -> TaskMinionRepository:
    return TaskMinionRepository(db)
