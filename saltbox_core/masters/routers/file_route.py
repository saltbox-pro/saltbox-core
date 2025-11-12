from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse

from saltbox_core.masters.schemas.file_manage_schemas import FileAction
from saltbox_core.masters.schemas.master_schemas import MastersActions
from saltbox_core.masters.services.file_manager.base_file_manager import (
    BaseFileManager,
    FileOperationResponse,
    FileRequest,
    TransferRequest,
    UploadRequest,
)
from saltbox_core.masters.services.file_manager.sshfs_file_manager import get_file_manager
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.discovery_client.schemas import GatewayEndpointConfig

router = APIRouter(prefix='/file', tags=['File'])


@router.post(
    '/folder',
    openapi_extra=GatewayEndpointConfig(
        policy='core.masters.base',  # TODO: deleate opa fields
        action=MastersActions.ACCEPT,
    ).model_dump(by_alias=True)
)
async def create_folder(
        request: FileRequest,
        manager: Annotated[BaseFileManager, Depends(get_file_manager)]
    ) -> FileOperationResponse:
    return await manager.create_folder(request=request)


@router.post(
    '/preview',
    openapi_extra=GatewayEndpointConfig(
        policy='core.masters.base',  # TODO: deleate opa fields
        action=MastersActions.ACCEPT,
    ).model_dump(by_alias=True),
    response_class=FileResponse
)
async def preview(
        request: FileRequest,
        manager: Annotated[BaseFileManager, Depends(get_file_manager)]
    ) -> FileResponse:
    return await manager.preview(request=request)


@router.post(
    '/upload',
    openapi_extra=GatewayEndpointConfig(
        policy='core.masters.base',  # TODO: deleate opa fields
        action=MastersActions.ACCEPT,
    ).model_dump(by_alias=True)
)
async def upload_file(
        manager: Annotated[BaseFileManager, Depends(get_file_manager)],
        mid: Annotated[PyObjectId, Form(...)],
        file: Annotated[UploadFile, File(...)],
        dst: Annotated[str, Form("")]
    ) -> FileOperationResponse:
    request = UploadRequest(mid=mid, path=dst, file=file, mode=None)
    return await manager.upload(request=request)


@router.post(
    '/transfer/{action}',
    openapi_extra=GatewayEndpointConfig(
        policy='core.masters.base',  # TODO: deleate opa fields
        action=MastersActions.ACCEPT,
    ).model_dump(by_alias=True)
)
async def transfer(
        action: str,
        src: str,
        dst: str,
        manager: Annotated[BaseFileManager, Depends(get_file_manager)]
    ) -> FileOperationResponse:
    transfer_request = TransferRequest(src=src, dst=dst, action=FileAction(action))
    return await manager.transfer(request=transfer_request)


@router.delete(
    '/',
    openapi_extra=GatewayEndpointConfig(
        policy='core.masters.base',  # TODO: deleate opa fields
        action=MastersActions.ACCEPT,
    ).model_dump(by_alias=True)
)
async def delete(
        request: FileRequest,
        manager: Annotated[BaseFileManager, Depends(get_file_manager)]
    ) -> FileOperationResponse:
    return await manager.deleate(request=request)
