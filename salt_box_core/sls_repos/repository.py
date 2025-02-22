from typing import Annotated, ClassVar

from fastapi import Depends
from pymongo.asynchronous.database import AsyncDatabase

from salt_box_core.db.mongo.config import get_mongo
from salt_box_core.db.mongo.repository_base import BaseMongoRepository
from salt_box_core.sls_repos.schemas.settings_schemas import SettingsSlsRepoModel


class SettingsSlsRepoRepository(BaseMongoRepository[SettingsSlsRepoModel]):
    class Meta:
        collection_name = 'settings_sls_repos'
        auto_now_add_fields: ClassVar[list[str]] = ['created']
        auto_now_fields: ClassVar[list[str]] = ['modified']


def get_sls_repo_repository(db: Annotated[AsyncDatabase, Depends(get_mongo)]) -> SettingsSlsRepoRepository:
    return SettingsSlsRepoRepository(db)
