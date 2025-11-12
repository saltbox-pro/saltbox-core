import shutil
from pathlib import Path
from typing import override

from fastapi import UploadFile
from fastapi.responses import FileResponse

from saltbox_core.exceptions import FileNotFoundException
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
        target: Path = self._resolve_minion_path(mid=request.mid, relative=request.path)
        target.mkdir(parents=True, exist_ok=True)
        return FileOperationResponse(mid=request.mid)

    @override
    async def preview(
        self,
        *,
        request: FileRequest
    ) -> FileResponse:
        target: Path = self._resolve_minion_path(mid=request.mid, relative=request.path)
        if not target.exists() or not target.is_file():
            msg = f"Displayed file '{target}' on the {request.mid} minion was not found"
            raise FileNotFoundException(msg)
        displayed_file = FileResponse(path=target, filename=target.name)
        return displayed_file

    @override
    async def upload(
        self,
        *,
        request: UploadRequest
    ) -> FileOperationResponse:
        target_dir: Path = self._resolve_minion_path(mid=request.mid, relative=request.path)
        target_dir.mkdir(parents=True, exist_ok=True)

        uploaded_file: UploadFile = request.file
        target_path: Path = target_dir / uploaded_file.filename
        with target_path.open(mode='wb') as out:
            shutil.copyfileobj(fsrc=uploaded_file.file, fdst=out)

        return FileOperationResponse(mid=request.mid)

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
