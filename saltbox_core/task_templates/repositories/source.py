from typing import Annotated, Any, ClassVar, TypeVar

import pymongo
from fastapi import Depends
from pydantic import BaseModel
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.operations import _IndexKeyHint

from saltbox_core.task_templates.schemas.source import TemplateSourceModel
from saltbox_sdk.db.mongo.config import get_mongo
from saltbox_sdk.db.mongo.repository_base import BaseMongoRepository

ModelType = TypeVar('ModelType', bound=BaseModel)


class TemplateSourceRepository(BaseMongoRepository[TemplateSourceModel]):
    class Meta:
        collection_name = 'task_tpl_sources'
        auto_now_add_fields: ClassVar[list[str]] = ['created']
        auto_now_fields: ClassVar[list[str]] = ['modified']
        collection_index_to_keys: ClassVar[dict[str, _IndexKeyHint]] = {
            'url_unique_index_asc': [('repo_url', pymongo.ASCENDING)],
            'name_unique_index': [('name', pymongo.ASCENDING)],
            'local_path_unique_index_asc': [('local_path', pymongo.ASCENDING)],
        }
        collection_index_options: ClassVar[dict[str, dict[str, Any]]] = {
            'url_unique_index_asc': {'unique': True, 'sparse': True},
            'name_unique_index': {'unique': True},
            'local_path_unique_index_asc': {'unique': True},
        }


def get_template_source_repository(db: Annotated[AsyncDatabase, Depends(get_mongo)]) -> TemplateSourceRepository:
    return TemplateSourceRepository(db)
