from typing import Annotated, ClassVar

from fastapi import Depends
from pymongo.asynchronous.database import AsyncDatabase

from saltbox_core.tasks.schemas.tasks_status import TaskStatusModel
from saltbox_sdk.db.mongo.config import get_mongo
from saltbox_sdk.db.mongo.repository_base import BaseMongoRepository


class TaskStatusRepository(BaseMongoRepository[TaskStatusModel]):
    class Meta:
        collection_name = 'task_statuses'
        auto_now_add_fields: ClassVar[list[str]] = ['created']
        auto_now_fields: ClassVar[list[str]] = ['modified']


def get_task_status_repository(db: Annotated[AsyncDatabase, Depends(get_mongo)]) -> TaskStatusRepository:
    return TaskStatusRepository(db)
