import asyncio
import shutil
from pathlib import Path
from typing import Annotated, Any, TypeVar, overload, override

from fastapi import Depends
from pydantic import BaseModel
from redis.asyncio import Redis

from saltbox_core.config import SETTINGS, logger
from saltbox_core.settings.repository import (
    SettingsSlsRepoRepository,
    get_sls_repo_repository,
)
from saltbox_core.settings.schemas.sls_repos_schemas import (
    SettingsSlsRepoCreateSchema,
    SettingsSlsRepoModel,
    SettingsSlsRepoUpdateSchema,
)
from saltbox_core.settings.tasks import sync_sls_repo_task, sync_sls_repos_to_serve_dir
from saltbox_core.tasks.services.tasks_templates import TaskTemplateService
from saltbox_sdk.db.mongo.schemas_base import PyObjectId, SortOrder
from saltbox_sdk.db.schemas_base import PaginatedResponse
from saltbox_sdk.fastapi_utils.dependencies import get_redis_dep
from saltbox_sdk.serivces.mongo_base_service import MongoBaseService

ProjectionModel = TypeVar('ProjectionModel', bound=BaseModel)


class SettingsSlsRepoService(
    MongoBaseService[
        SettingsSlsRepoRepository, SettingsSlsRepoModel, SettingsSlsRepoCreateSchema, SettingsSlsRepoUpdateSchema
    ]
):
    def __init__(self, repo: SettingsSlsRepoRepository, redis: Redis) -> None:
        self._redis = redis
        super().__init__(repo)

    @overload
    async def get_list_paginated(
        self,
        query: dict[str, Any] | None,
        limit: int,
        skip: int,
        *,
        sort: dict[str, SortOrder] | None = None,
    ) -> PaginatedResponse[SettingsSlsRepoModel]: ...

    @overload
    async def get_list_paginated(
        self,
        query: dict[str, Any] | None,
        limit: int,
        skip: int,
        projection_model: type[ProjectionModel],
        *,
        sort: dict[str, SortOrder] | None = None,
    ) -> PaginatedResponse[ProjectionModel]: ...

    @override
    async def get_list_paginated(
        self,
        query: dict[str, Any] | None = None,
        limit: int = 0,
        skip: int = 0,
        projection_model: type[ProjectionModel] | None = None,
        *,
        sort: dict[str, SortOrder] | None = None,
    ) -> PaginatedResponse[SettingsSlsRepoModel] | PaginatedResponse[ProjectionModel]:
        total = await self.repo.count(query)

        lockers = await self._get_repo_lockers()

        data = await self.repo.get_list(
            query, limit=limit, skip=skip, projection_model=projection_model or SettingsSlsRepoModel, sort=sort
        )
        for item in data:
            if hasattr(item, 'repo_url') and hasattr(item, 'locked'):
                item.locked = True if item.repo_url in lockers else False

        if projection_model is None:
            return PaginatedResponse[SettingsSlsRepoModel](total=total, data=data)

        return PaginatedResponse[ProjectionModel](total=total, data=data)

    async def _get_repo_lockers(self) -> list[str]:
        """Get list of locked repositories.
        Lock string format: 'repo_lock:https://user:token@domain.ru/path/to/repo.git'
        """
        keys = await self._redis.keys('repo_lock:*')
        lockers = [key.decode('utf-8').split(':', 1)[-1] for key in keys]
        logger.debug('Locked repositories: %s', lockers)
        return lockers

    async def set_activity_state(self, sid: PyObjectId, state: bool) -> SettingsSlsRepoModel:
        document = await self.get(sid)
        if document.is_active == state:
            return document
        result = await self.update(query=sid, data={'is_active': state})
        await self.sync_to_serve_dir()
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
        await sync_sls_repos_to_serve_dir.kiq()


def get_sls_repo_service(
    repo: Annotated[SettingsSlsRepoRepository, Depends(get_sls_repo_repository)],
    redis: Annotated[Redis, Depends(get_redis_dep)],
) -> SettingsSlsRepoService:
    return SettingsSlsRepoService(repo=repo, redis=redis)
