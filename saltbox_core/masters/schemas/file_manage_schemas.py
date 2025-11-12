from enum import StrEnum

from fastapi import UploadFile
from pydantic import BaseModel, Field

from saltbox_sdk.db.mongo.schemas_base import PyObjectId


class FileOperationResponse(BaseModel):
    mid: PyObjectId
    path: str | None = None


class FileRequest(BaseModel):
    mid: PyObjectId
    path: str = Field(..., examples=['/temp/some_file.txt'])
    mode: int | None = Field(None, examples=[644, 777, 765])


class UploadRequest(FileRequest):
    file: UploadFile


class FileAction(StrEnum):
    copy = 'copy'
    move = 'move'
    rename = 'rename'


class TransferRequest(BaseModel):
    src: str
    dst: str
    action: FileAction
