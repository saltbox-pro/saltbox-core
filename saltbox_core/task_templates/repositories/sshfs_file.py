from typing import Annotated, Any, ClassVar, TypeVar

import pymongo
from fastapi import Depends
from pydantic import BaseModel
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.operations import _IndexKeyHint

from saltbox_core.task_templates.schemas.sshfs_file import SshfsFileModel
from saltbox_sdk.db.mongo.config import get_mongo
from saltbox_sdk.db.mongo.repository_base import BaseMongoRepository

ModelType = TypeVar('ModelType', bound=BaseModel)


class SshfsFileRepository(BaseMongoRepository[SshfsFileModel]):
    class Meta:
        collection_name = 'task_template_files'
        auto_now_add_fields: ClassVar[list[str]] = ['created']
        auto_now_fields: ClassVar[list[str]] = ['modified']
        collection_index_to_keys: ClassVar[dict[str, _IndexKeyHint]] = {
            'rel_path_unique_index': [('rel_path', pymongo.ASCENDING)],
        }
        collection_index_options: ClassVar[dict[str, dict[str, Any]]] = {
            'rel_path_unique_index': {'unique': True},
        }


def get_sshfs_file_repository(db: Annotated[AsyncDatabase, Depends(get_mongo)]) -> SshfsFileRepository:
    return SshfsFileRepository(db)
