from typing import Annotated, Any, override

from fastapi import Depends
from pymongo.asynchronous.client_session import AsyncClientSession

from saltbox_core.config import logger
from saltbox_core.task_templates.repositories.sshfs_file import SshfsFileRepository, get_sshfs_file_repository
from saltbox_core.task_templates.schemas.sshfs_file import (
    SshfsFileCreateSchema,
    SshfsFileModel,
    SshfsFileUpdateSchema,
)
from saltbox_core.task_templates.utils.manifest import SshfsSync, get_sshfs_sync
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.serivces.mongo_base_service import MongoBaseService


class SshfsFileService(
    MongoBaseService[
        SshfsFileRepository,
        SshfsFileModel,
        SshfsFileCreateSchema,
        SshfsFileUpdateSchema,
    ]
):
    def __init__(
        self,
        repo: SshfsFileRepository,
        sshfs_sync_service: SshfsSync,
    ) -> None:
        super().__init__(repo=repo)
        self._sshfs_sync_service = sshfs_sync_service

    @override
    async def delete(
        self,
        query: dict[str, Any] | PyObjectId,
        *,
        session: AsyncClientSession | None = None,
    ) -> int:
        if isinstance(query, PyObjectId):
            query = {'_id': query}
        file = await self.get(query=query, session=session)
        if not file:
            return 0
        try:
            await self._sshfs_sync_service.remove(file)
        except Exception as e:
            logger.error('Failed to remove file from SSHFS: %s', e)
            raise
        return await self.repo.delete(query=query, session=session)

    @override
    async def delete_many(
        self,
        query: dict[str, Any],
        *,
        session: AsyncClientSession | None = None,
    ) -> int:
        files = await self.get_list(query=query, skip=0, limit=0)
        if not files:
            return 0
        # Remove files from SSHFS
        for file in files:
            try:
                await self._sshfs_sync_service.remove(file)
            except Exception as e:
                logger.error('Failed to remove file from SSHFS: %s', e)
                raise

        return await self.repo.delete_many(query=query, session=session)


def get_sshfs_file_service(
    repo: Annotated[SshfsFileRepository, Depends(get_sshfs_file_repository)],
    sshfs_sync_service: Annotated[SshfsSync, Depends(get_sshfs_sync)],
) -> SshfsFileService:
    return SshfsFileService(repo=repo, sshfs_sync_service=sshfs_sync_service)
