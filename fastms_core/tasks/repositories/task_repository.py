from typing import Annotated

from fastapi import Depends
from pymongo.asynchronous.database import AsyncDatabase

from fastms_core.db.mongo.config import get_mongo
from fastms_core.db.mongo.repository_base import BaseMongoRepository
from fastms_core.tasks.schemas.task_schemas import TaskModel


class TaskRepository(BaseMongoRepository[TaskModel]):
    class Meta:
        collection_name = 'tasks'
        auto_now_add_fields = ['created']
        auto_now_fields = ['modified']


def get_task_repository(db: Annotated[AsyncDatabase, Depends(get_mongo)]) -> TaskRepository:
    return TaskRepository(db)
