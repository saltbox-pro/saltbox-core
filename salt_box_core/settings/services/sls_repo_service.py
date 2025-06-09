import asyncio
import shutil
from pathlib import Path
from typing import Annotated

from fastapi import Depends

from salt_box_core.config import SETTINGS, logger
from salt_box_core.db.mongo.schemas_base import PyObjectId
from salt_box_core.settings.repository import (
    SettingsSlsRepoRepository,
    get_sls_repo_repository,
)
from salt_box_core.settings.schemas.sls_repos_schemas import (
    SettingsSlsRepoCreateSchema,
    SettingsSlsRepoModel,
    SettingsSlsRepoUpdateSchema,
)
from salt_box_core.settings.tasks import sync_sls_repo_task
from salt_box_core.tasks.services.tasks_templates import TaskTemplateService
from salt_box_core.utilities.git_repo_helper import sync_sls_repos_to_serve_dir
from salt_box_core.utilities.serivces.mongo_base_service import MongoBaseService, ProjectionModel


class SettingsSlsRepoService(
    MongoBaseService[
        SettingsSlsRepoRepository, SettingsSlsRepoModel, SettingsSlsRepoCreateSchema, SettingsSlsRepoUpdateSchema
    ]
):
    async def set_activity_state(self, sid: PyObjectId, state: bool) -> SettingsSlsRepoModel:
        document = await self.get(sid)
        if document.is_active == state:
            return document
        result = await self.update(query=sid, data={'is_active': state})
        await self.sync_to_serve_dir()  # TODO (akraman) Async in taskiq
        return result

    async def activate(self, sid: PyObjectId) -> SettingsSlsRepoModel:
        return await self.set_activity_state(sid=sid, state=True)

    async def deactivate(self, sid: PyObjectId) -> SettingsSlsRepoModel:
        return await self.set_activity_state(sid=sid, state=False)

    async def sync_all(self) -> list[str]:
        active_repos = await self.get_list(query={'is_active': True}, skip=0, limit=0)
        task_ids = []
        for repo in active_repos:
            try:
                task_id = await self.sync(repo.id)
                task_ids.append(task_id)
            except Exception as e:
                msg = f'{e!s}'
                logger.error(msg)
                raise
        return task_ids

    async def delete_and_clean(self, sid: PyObjectId, tpl_service: TaskTemplateService) -> None:
        repo_settings = await self.get(sid)
        # Remove all templates from this repo
        try:
            deleted_count = await tpl_service.delete_many({'repo_id': sid})
            logger.debug('deleted_count: %s', deleted_count)
        except Exception as e:
            msg = f'{e!s}'
            logger.error(msg)
            raise

        try:
            path = Path(SETTINGS.local_repos_dir) / repo_settings.local_path
            logger.debug('Remove folder: %s', path)
            if path.exists():
                await asyncio.to_thread(shutil.rmtree, path)
        except Exception as e:
            msg = f'{e!s}'
            logger.error(msg)
            raise

        await self.delete(sid)

        # Delete from serve directory
        await self.sync_to_serve_dir()


    async def sync(self, sid: PyObjectId) -> str:
        task = await sync_sls_repo_task.kiq(str(sid))
        return task.task_id

    async def sync_to_serve_dir(self) -> None:
        await sync_sls_repos_to_serve_dir(self.repo)


def get_sls_repo_service(
    repo: Annotated[SettingsSlsRepoRepository, Depends(get_sls_repo_repository)],
) -> SettingsSlsRepoService:
    return SettingsSlsRepoService(repo)
