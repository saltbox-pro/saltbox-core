from typing import Annotated, Any, ClassVar, TypeVar

import pymongo
from fastapi import Depends
from pydantic import BaseModel
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.operations import _IndexKeyHint

from saltbox_core.task_templates.schemas.template import TaskTemplateModel
from saltbox_sdk.db.mongo.config import get_mongo
from saltbox_sdk.db.mongo.repository_base import BaseMongoRepository

ModelType = TypeVar('ModelType', bound=BaseModel)


class TaskTemplateRepository(BaseMongoRepository[TaskTemplateModel]):
    class Meta:
        collection_name = 'task_tpls'
        auto_now_add_fields: ClassVar[list[str]] = ['created']
        auto_now_fields: ClassVar[list[str]] = ['modified']
        collection_index_to_keys: ClassVar[dict[str, _IndexKeyHint]] = {
            'name_unique_index': [('name', pymongo.ASCENDING)],
        }
        collection_index_options: ClassVar[dict[str, dict[str, Any]]] = {
            'name_unique_index': {'unique': True},
        }


def get_task_template_repository(db: Annotated[AsyncDatabase, Depends(get_mongo)]) -> TaskTemplateRepository:
    return TaskTemplateRepository(db)
