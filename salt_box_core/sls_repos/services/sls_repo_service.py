from typing import Annotated, Any

from fastapi import Depends

# from salt_box_core.config import logger
from salt_box_core.db.mongo.schemas_base import PyObjectId
from salt_box_core.sls_repos.repository import SettingsSlsRepoRepository, get_sls_repo_repository
from salt_box_core.sls_repos.schemas import (
    SettingsSlsRepoCreateSchema,
    SettingsSlsRepoModel,
    SettingsSlsRepoUpdateSchema,
)
from salt_box_core.utilities.serivces.mongo_base_service import MongoBaseService


class SettingsSlsRepoService(
    MongoBaseService[
        SettingsSlsRepoRepository, SettingsSlsRepoModel, SettingsSlsRepoCreateSchema, SettingsSlsRepoUpdateSchema
    ]
):
    async def activate(self, sid: PyObjectId) -> SettingsSlsRepoModel:
        document = await self.get(sid)
        if document.is_active:
            return document

        return await self.update(query=sid, data={'is_active': True})

    async def deactivate(self, sid: PyObjectId) -> SettingsSlsRepoModel:
        document = await self.get(sid)
        if not document.is_active:
            return document
        return await self.update(query=sid, data={'is_active': False})

    async def sync_all(self) -> None:
        pass

    async def sync(self, sid: PyObjectId) -> Any:
        pass


def get_sls_repo_service(
    repo: Annotated[SettingsSlsRepoRepository, Depends(get_sls_repo_repository)],
) -> SettingsSlsRepoService:
    return SettingsSlsRepoService(repo)
