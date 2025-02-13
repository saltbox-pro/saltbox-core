from typing import Annotated, ClassVar

from fastapi import Depends
from pymongo.asynchronous.database import AsyncDatabase

from salt_box_core.db.mongo.config import get_mongo
from salt_box_core.db.mongo.repository_base import BaseMongoRepository
from salt_box_core.tasks.schemas.task_template_schemas import TaskTemplateModel


class TaskTemplateRepository(BaseMongoRepository[TaskTemplateModel]):
    class Meta:
        collection_name = 'task_templates'
        auto_now_add_fields: ClassVar[list[str]] = ['created']
        auto_now_fields: ClassVar[list[str]] = ['modified']


def get_task_template_repository(db: Annotated[AsyncDatabase, Depends(get_mongo)]) -> TaskTemplateRepository:
    return TaskTemplateRepository(db)
