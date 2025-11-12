from enum import Enum

from fastapi import UploadFile
from pydantic import BaseModel, Field

from saltbox_sdk.db.mongo.schemas_base import PyObjectId


# class SyncStatus(Enum):
#     failed = 'failed'
#     sshfs = 'sshfs_synced'
#     salt_minion = 'salt_minion_synced'
#     full = 'full_synced'


class FileOperationResponse(BaseModel):
    mid: PyObjectId
    # status: SyncStatus
    details: str | None = None


class FileRequest(BaseModel):
    mid: PyObjectId
    path: str = Field(..., examples=['~/etc/rc.local'])
    mode: int | None = Field(None, examples=[644, 777, 765])


class UploadRequest(BaseModel):
    file: UploadFile
    dst: str


class FileAction(Enum):
    copy = 'copy'
    move = 'move'
    rename = 'rename'


class MoveRequest(BaseModel):
    src: str
    dst: str


class TransferRequest(MoveRequest):
    action: FileAction
