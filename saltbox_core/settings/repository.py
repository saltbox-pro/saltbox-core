from typing import Annotated, ClassVar

from fastapi import Depends
from pymongo.asynchronous.database import AsyncDatabase

from saltbox_core.settings.schemas.sls_repos_schemas import SettingsSlsRepoModel
from saltbox_sdk.db.mongo.config import get_mongo
from saltbox_sdk.db.mongo.repository_base import BaseMongoRepository


class SettingsSlsRepoRepository(BaseMongoRepository[SettingsSlsRepoModel]):
    class Meta:
        collection_name = 'settings_sls_repos'
        auto_now_add_fields: ClassVar[list[str]] = ['created']
        auto_now_fields: ClassVar[list[str]] = ['modified']


def get_sls_repo_repository(db: Annotated[AsyncDatabase, Depends(get_mongo)]) -> SettingsSlsRepoRepository:
    return SettingsSlsRepoRepository(db)
