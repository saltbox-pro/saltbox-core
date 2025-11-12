import abc
from abc import abstractmethod
from pathlib import Path

from saltbox_core.masters.schemas.file_manage_schemas import (
    FileOperationResponse,
    FileRequest,
    TransferRequest,
    UploadRequest,
)
from saltbox_sdk.db.mongo.schemas_base import PyObjectId


class BaseFileManager(abc.ABC):

    _SSHFS_ROOT = Path('/srv/sshfs/minions')

    @abstractmethod
    async def create_folder(self, *, request: FileRequest) -> FileOperationResponse: ...

    @abstractmethod
    async def preview(self, *, request: FileRequest) -> FileOperationResponse: ...

    @abstractmethod
    async def upload(self, *, request: UploadRequest) -> FileOperationResponse: ...

    @abstractmethod
    async def transfer(self, *, request: TransferRequest) -> FileOperationResponse: ...

    @abstractmethod
    async def deleate(self, *, request: FileRequest) -> FileOperationResponse: ...

    def _get_minion_root(self, mid: PyObjectId) -> Path:
        minion_root: Path = self._SSHFS_ROOT / str(mid) / 'data'
        minion_root.mkdir(parents=True, exist_ok=True)
        return minion_root

    def _resolve_minion_path(self, *, mid: PyObjectId, relative: str | None) -> Path:
        base: Path = self._get_minion_root(mid=mid)
        if relative:
            return base / relative.lstrip('/')
        return base
