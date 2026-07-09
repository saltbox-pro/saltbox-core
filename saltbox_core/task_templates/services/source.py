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
    TemplateSourceCreateLocalSchema,
    TemplateSourceCreateSchema,
    TemplateSourceImportFromGitSchema,
    TemplateSourceImportFromMountedSchema,
    TemplateSourceModel,
    TemplateSourceUpdateSchema,
)
from saltbox_core.task_templates.services.sshfs_file import SshfsFileService, get_sshfs_file_service
from saltbox_core.task_templates.services.template import TaskTemplateService, get_task_tpl_service
from saltbox_core.tasks.services.task import TaskService, get_task_service
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

    async def create_from_url(
        self,
        data: TemplateSourceImportFromGitSchema,
        *,
        session: AsyncClientSession | None = None,
    ) -> PyObjectId:
        if data.repo_url.port and data.repo_url.port not in (80, 443):
            clean_url = f'{data.repo_url.scheme}://{data.repo_url.host}:{data.repo_url.port}{data.repo_url.path}'
        else:
            clean_url = f'{data.repo_url.scheme}://{data.repo_url.host}{data.repo_url.path}'
        user = data.repo_user or data.repo_url.username
        password = data.repo_pass or data.repo_url.password

        obj_in = {
            'name': data.name,
            'description': data.description,
            'source_type': SourceType.GIT_REPO,
            'namespace': None,
            'repo_url': clean_url,
            'repo_user': user,
            'repo_pass': password,
            'branch': data.branch,
            'local_path': uuid.uuid4().hex,
            'state': SourceState.PENDING,
            'current_operation': SourceOperation.DISCOVER,
            'last_error': None,
            'synced_at': None,
        }
        return await self.create(data=obj_in, session=session)

    async def create_from_mounted_path(
        self,
        data: TemplateSourceImportFromMountedSchema,
        *,
        session: AsyncClientSession | None = None,
    ) -> PyObjectId:
        obj_in = {
            'name': data.name,
            'description': '',
            'source_type': SourceType.MOUNTED_REPO,
            'namespace': None,
            'repo_mounted_path': data.repo_mounted_path,
            'local_path': uuid.uuid4().hex,
            'state': SourceState.PENDING,
            'current_operation': SourceOperation.DISCOVER,
            'last_error': None,
            'synced_at': None,
        }
        return await self.create(data=obj_in, session=session)

    async def create_local(
        self,
        data: TemplateSourceCreateLocalSchema,
        *,
        session: AsyncClientSession | None = None,
    ) -> PyObjectId:
        obj_in = {
            'name': data.name,
            'description': data.description,
            'source_type': SourceType.LOCAL_BUNDLE,
            'namespace': data.namespace,
            'local_path': uuid.uuid4().hex,
            'state': SourceState.PENDING,
            'current_operation': SourceOperation.DISCOVER,
            'last_error': None,
            'synced_at': None,
        }
        return await self.create(data=obj_in, session=session)

    async def create_from_archive(
        self,
        name: str,
        description: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> PyObjectId:
        obj_in = {
            'name': name,
            'description': description,
            'source_type': SourceType.ARCHIVE_BUNDLE,
            'namespace': None,
            'local_path': uuid.uuid4().hex,
            'state': SourceState.PENDING,
            'current_operation': None,
            'last_error': None,
            'synced_at': None,
        }
        return await self.create(data=obj_in, session=session)

    @override
    async def delete(
        self,
        query: dict[str, Any] | PyObjectId,
        *,
        session: AsyncClientSession | None = None,
    ) -> int:
        async with get_mongo_session_with_transaction(session) as s:
            source = await self.get(query=query, session=s)
            delete_query = {'source_id': source.id}

            # TODO: Check for dependent tasks before deleting templates

            await self._template_service.delete_many(query=delete_query, session=s)
            await self._file_service.delete_many(query=delete_query, session=s)

            local_path = Path(SETTINGS.local_repos_dir) / source.local_path
            if local_path.exists() and local_path.is_dir():
                src_root = local_path / source.root
                if src_root.exists() and src_root.is_dir():
                    serve_dir = SETTINGS.salt_modules_serve_dir
                    for entry in src_root.iterdir():
                        serve_entry = serve_dir / entry.name
                        if serve_entry.exists() or serve_entry.is_symlink():
                            try:
                                if serve_entry.is_dir() and not serve_entry.is_symlink():
                                    shutil.rmtree(serve_entry)
                                else:
                                    serve_entry.unlink(missing_ok=True)
                            except OSError as e:
                                logger.error('Failed to remove entry from serve_dir: %s', e)
                                raise
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
    template_service: Annotated[TaskTemplateService, Depends(get_task_tpl_service)],
    file_service: Annotated[SshfsFileService, Depends(get_sshfs_file_service)],
    task_service: Annotated[TaskService, Depends(get_task_service)],
) -> TemplateSourceService:
    return TemplateSourceService(
        repo=repo, template_service=template_service, file_service=file_service, task_service=task_service
    )
