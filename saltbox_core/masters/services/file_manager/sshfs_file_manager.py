import os
from typing import override

from saltbox_core.masters.schemas.file_manage_schemas import SyncStatus
from saltbox_core.masters.services.file_manager.base_file_manager import (
    BaseFileManager,
    FileOperationResponse,
    FileRequest,
    TransferRequest,
    UploadRequest,
)


class SshfsFileManager(BaseFileManager):

    @override
    async def create_folder(
        self,
        *,
        request: FileRequest
    ) -> FileOperationResponse:
        target = self._resolve_minion_path(mid=request.mid, relative=request.path)
        target.mkdir(parents=True, exist_ok=True)
        return FileOperationResponse(mid=request.mid)

    @override
    async def preview(
        self,
        *,
        request: FileRequest
    ) -> FileOperationResponse: ...

    @override
    async def upload(
        self,
        *,
        request: UploadRequest
    ) -> FileOperationResponse: ...

    @override
    async def transfer(
        self,
        *,
        request: TransferRequest
    ) -> FileOperationResponse: ...

    @override
    async def deleate(
        self,
        *,
        request: FileRequest
    ) -> FileOperationResponse: ...


# TODO: There must be a sub.manager
def get_file_manager() -> SshfsFileManager:
    return SshfsFileManager()
