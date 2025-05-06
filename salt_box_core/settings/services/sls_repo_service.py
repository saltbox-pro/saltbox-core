import asyncio
import shutil
import uuid
from pathlib import Path
from typing import Annotated, overload, override

from fastapi import Depends

from salt_box_core.config import SETTINGS, logger
from salt_box_core.db.mongo.config import get_mongo_db
from salt_box_core.db.mongo.schemas_base import PyObjectId
from salt_box_core.event_bus.masters_bus import send_message_to_master
from salt_box_core.masters.repositories.master_repository import MasterRepository
from salt_box_core.masters.services.master_service import MasterService
from salt_box_core.settings.repository import (
    SettingsSlsRepoRepository,
    get_sls_repo_repository,
)
from salt_box_core.settings.schemas.event_bus_schemas import ListSlsReposMessage, MasterMessageSlsRepoModel
from salt_box_core.settings.schemas.sls_repos_schemas import (
    SettingsSlsRepoCreateSchema,
    SettingsSlsRepoModel,
    SettingsSlsRepoUpdateSchema,
)
from salt_box_core.settings.tasks import sync_sls_repo_task
from salt_box_core.tasks.services.tasks_templates import TaskTemplateService
from salt_box_core.utilities.serivces.mongo_base_service import MongoBaseService, ProjectionModel


# TODO Make generic send_message_to_every_master() in masters_bus
async def notify_masters() -> None:
    mongo_db = get_mongo_db()
    master_repo = MasterRepository(mongo_db)
    sls_repo_repo = SettingsSlsRepoRepository(mongo_db)
    masters = await MasterService(master_repo).get_list(query={}, skip=0, limit=0)
    active_repos = await SettingsSlsRepoService(sls_repo_repo).get_list(query={'is_active': True}, skip=0, limit=0)
    msg_repos = [MasterMessageSlsRepoModel(**repo.dict()) for repo in active_repos]
    for m_obj in masters:
        msg = ListSlsReposMessage(repos=msg_repos, master=m_obj.name)
        await send_message_to_master(msg, 'sync_repos')


class SettingsSlsRepoService(
    MongoBaseService[
        SettingsSlsRepoRepository, SettingsSlsRepoModel, SettingsSlsRepoCreateSchema, SettingsSlsRepoUpdateSchema
    ]
):
    @overload
    async def create(self, data: SettingsSlsRepoCreateSchema) -> SettingsSlsRepoModel: ...

    @overload
    async def create(
        self, data: SettingsSlsRepoCreateSchema, projection_model: type[ProjectionModel]
    ) -> ProjectionModel: ...

    @override
    async def create(
        self, data: SettingsSlsRepoCreateSchema, projection_model: type[ProjectionModel] | None = None
    ) -> SettingsSlsRepoModel | ProjectionModel:
        if await self.repo.exists({'local_path': data.local_path}):
            unique_suffix = str(uuid.uuid4())[:8]
            data.local_path = f'{data.local_path}_{unique_suffix}'

        if projection_model:
            return await super().create(data, projection_model)
        return await super().create(data)

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
            path = Path(SETTINGS.local_repos_path) / repo_settings.local_path
            logger.debug('Remove folder: %s', path)
            if path.exists():
                await asyncio.to_thread(shutil.rmtree, path)
        except Exception as e:
            msg = f'{e!s}'
            logger.error(msg)
            raise

        await self.delete(sid)

    async def sync(self, sid: PyObjectId) -> str:
        task = await sync_sls_repo_task.kiq(str(sid))
        return task.task_id


def get_sls_repo_service(
    repo: Annotated[SettingsSlsRepoRepository, Depends(get_sls_repo_repository)],
) -> SettingsSlsRepoService:
    return SettingsSlsRepoService(repo)
