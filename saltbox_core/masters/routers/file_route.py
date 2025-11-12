from typing import Annotated

from fastapi import APIRouter, Depends

from saltbox_core.masters.schemas.file_manage_schemas import FileAction, MoveRequest
from saltbox_core.masters.schemas.master_schemas import MastersActions
from saltbox_core.masters.services.file_manager.base_file_manager import (
    BaseFileManager,
    FileOperationResponse,
    FileRequest,
    TransferRequest,
    UploadRequest,
)
from saltbox_core.masters.services.file_manager.sshfs_file_manager import get_file_manager
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


@router.get(
    '/preview/{file_path:path}',
    openapi_extra=GatewayEndpointConfig(
        policy='core.masters.base',  # TODO: deleate opa fields
        action=MastersActions.ACCEPT,
    ).model_dump(by_alias=True)
)
async def preview(
        request: FileRequest,
        manager: Annotated[BaseFileManager, Depends(get_file_manager)]
    ) -> FileOperationResponse:
    return await manager.preview(request=request)


@router.get(
    '/upload',
    openapi_extra=GatewayEndpointConfig(
        policy='core.masters.base',  # TODO: deleate opa fields
        action=MastersActions.ACCEPT,
    ).model_dump(by_alias=True)
)
async def upload_file(
        request: UploadRequest,
        manager: Annotated[BaseFileManager, Depends(get_file_manager)]
    ) -> FileOperationResponse:
    return await manager.upload(request=request)


@router.post(
    '/transfer/{action}',
    openapi_extra=GatewayEndpointConfig(
        policy='core.masters.base',  # TODO: deleate opa fields
        action=MastersActions.ACCEPT,
    ).model_dump(by_alias=True)
)
async def transfer(
        action: FileAction,
        body: MoveRequest,
        manager: Annotated[BaseFileManager, Depends(get_file_manager)]
    ) -> FileOperationResponse:
    request = TransferRequest(**body.model_dump(), action=action)
    return await manager.transfer(request=request)


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
