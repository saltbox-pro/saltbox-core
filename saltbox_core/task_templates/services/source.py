import shutil
import uuid
from pathlib import Path
from typing import Annotated, Any, override

from fastapi import Depends
from pymongo.asynchronous.client_session import AsyncClientSession

from saltbox_core.config import SETTINGS, logger
from saltbox_core.task_templates.repositories.source import TemplateSourceRepository, get_template_source_repository
from saltbox_core.task_templates.schemas.source import (
    SourceOperation,
    SourceState,
    SourceType,
    TemplateSourceCreateSchema,
    TemplateSourceModel,
    TemplateSourceUpdateSchema,
)
from saltbox_core.task_templates.services.sshfs_file import SshfsFileService, get_sshfs_file_service
from saltbox_core.task_templates.services.template import TaskTemplateService
from saltbox_core.tasks.services.task import TaskService, get_task_service
from saltbox_core.tasks.services.tasks_template import get_task_template_service
from saltbox_sdk.db.mongo.config import get_mongo_session_with_transaction
from saltbox_sdk.db.mongo.schemas_base import PyObjectId

# from saltbox_sdk.exceptions import ObjectNotFoundException
from saltbox_sdk.serivces.mongo_base_service import MongoBaseService


class TemplateSourceService(
    MongoBaseService[
        TemplateSourceRepository,
        TemplateSourceModel,
        TemplateSourceCreateSchema,
        TemplateSourceUpdateSchema,
    ]
):
    def __init__(
        self,
        repo: TemplateSourceRepository,
        template_service: TaskTemplateService,
        file_service: SshfsFileService,
        task_service: TaskService,
    ) -> None:
        super().__init__(repo)
        self._template_service = template_service
        self._file_service = file_service
        self._task_service = task_service

    @override
    async def create(
        self,
        data: TemplateSourceCreateSchema | dict[str, Any],
        *,
        session: AsyncClientSession | None = None,
    ) -> PyObjectId:
        if isinstance(data, TemplateSourceCreateSchema):
            data = data.model_dump()
        if data['source_type'] == SourceType.GIT_REPO and not data.get('repo_url'):
            msg = 'repo_url is required for git_repo source type.'
            raise ValueError(msg)
        if data['source_type'] != SourceType.GIT_REPO and (
            data.get('repo_url') or data.get('repo_user') or data.get('repo_pass')
        ):
            msg = 'repo_url, repo_user and repo_pass are only valid for git_repo source type.'
            raise ValueError(msg)
        data['local_path'] = uuid.uuid4().hex
        data['state'] = SourceState.PENDING
        data['current_operation'] = SourceOperation.DISCOVER
        data['last_error'] = None
        data['synced_at'] = None

        return await self.repo.create(data=data, session=session)

    @override
    async def delete(
        self,
        query: dict[str, Any] | PyObjectId,
        *,
        session: AsyncClientSession | None = None,
    ) -> int:
        async with get_mongo_session_with_transaction(session) as s:
            # Remove all related templates and files
            if isinstance(query, PyObjectId):
                source = await self.get(query=query, session=s)
            else:
                source = await self.get(query=query, session=s)
            source_id = source.id
            delete_query = {
                'source_id': source_id,
            }
            # Check for dependent tasks before deleting templates
            # if await self._task_repo.exists(
            #     query={
            #         'template_id': {
            #             '$in': await self._template_repo.get_list(
            #                 query=delete_query,
            #                 session=s,
            #             )
            #         },
            #         '$or': [
            #             {'task_type': 'policy'},
            #             {'status': {'$in': ['running', 'wait_minions']}},
            #         ],
            #     },
            #     session=s,
            # ):
            #     msg = 'Cannot delete source because there are tasks depending on its templates.'
            #     raise Exception(msg)
            await self._template_service.delete_many(query=delete_query, session=s)
            await self._file_service.delete_many(query=delete_query, session=s)

            local_path = Path(SETTINGS.local_repos_dir) / source.local_path
            if local_path and local_path.exists() and local_path.is_dir():
                try:
                    shutil.rmtree(local_path)
                except OSError as e:
                    logger.error('Failed to remove local path: %s', e)
                    raise
            return await super().delete(query=query, session=s)

    async def delete_many(
        self,
        query: dict[str, Any],
        *,
        session: AsyncClientSession | None = None,
    ) -> int:
        return await super().delete_many(query=query, session=session)


def get_tpl_source_service(
    repo: Annotated[TemplateSourceRepository, Depends(get_template_source_repository)],
    template_service: Annotated[TaskTemplateService, Depends(get_task_template_service)],
    file_service: Annotated[SshfsFileService, Depends(get_sshfs_file_service)],
    task_service: Annotated[TaskService, Depends(get_task_service)],
) -> TemplateSourceService:
    return TemplateSourceService(
        repo=repo, template_service=template_service, file_service=file_service, task_service=task_service
    )
