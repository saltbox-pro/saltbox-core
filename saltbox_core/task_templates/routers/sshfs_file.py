from typing import Annotated
from uuid import uuid4

import anyio
from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from saltbox_core.config import SETTINGS
from saltbox_core.task_templates.exceptions import OnlyUserFilesCanBeDeletedException
from saltbox_core.task_templates.schemas.source import TemplateSourceActions
from saltbox_core.task_templates.schemas.sshfs_file import (
    ManifestDigest,
    SshfsFileCreateSchema,
    SshfsFilePublicSchema,
    SshfsFileType,
    UnpackAs,
)
from saltbox_core.task_templates.services.source import TemplateSourceService, get_tpl_source_service
from saltbox_core.task_templates.services.sshfs_file import SshfsFileService, get_sshfs_file_service
from saltbox_core.task_templates.utils.orchestrator import SyncOrchestrator, get_sync_orchestrator
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.discovery_client.schemas import GatewayEndpointConfig

router = APIRouter(prefix='/task-template-sources', tags=['Task Templates / Files'])


@router.post(
    '/{source_id}/files',
    operation_id='sshfs_file_add',
    openapi_extra=GatewayEndpointConfig(
        policy='public',
        action=TemplateSourceActions.ADD_USER_FILE,
    ).model_dump(by_alias=True),
    status_code=status.HTTP_201_CREATED,
    response_model=SshfsFilePublicSchema,
)
async def add_file_to_source(
    source_id: PyObjectId,
    # rel_path: Annotated[str, Form(description='Destination path relative to sshfs root')],
    file: Annotated[UploadFile, File(description='File to upload')],
    orchestrator: Annotated[SyncOrchestrator, Depends(get_sync_orchestrator)],
    file_service: Annotated[SshfsFileService, Depends(get_sshfs_file_service)],
    source_service: Annotated[TemplateSourceService, Depends(get_tpl_source_service)],
    unpack_as: Annotated[
        UnpackAs | None,
        Form(description='Unpack as archive of specified format rather than place as is'),
    ] = None,
) -> SshfsFilePublicSchema:
    source = await source_service.get(query={'_id': source_id})
    if not file.filename:
        msg = 'File must have a filename'
        raise ValueError(msg)
    rel_path = file.filename
    if source.namespace:
        rel_path = f'{source.namespace}/{rel_path}'
    file_in = SshfsFileCreateSchema.model_validate(
        {
            'source_id': source_id,
            'file_type': SshfsFileType.USER,
            'rel_path': rel_path,
            'url': None,
            'checksum': '',
            'checksum_type': ManifestDigest.SHA256,
            'token': None,
            'unpack_as': unpack_as,
        }
    )

    file_id = await file_service.create(file_in)

    content = await file.read()
    SETTINGS.sshfs_tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = SETTINGS.sshfs_tmp_dir / f'{uuid4()}.upload'
    await anyio.Path(tmp_path).write_bytes(content)
    await orchestrator.add_user_file(source_id, file_id, tmp_path=tmp_path)
    return await file_service.get(query={'_id': file_id}, projection_model=SshfsFilePublicSchema)


@router.get(
    '/{source_id}/files',
    operation_id='sshfs_file_list',
    openapi_extra=GatewayEndpointConfig(
        policy='public',
        action=TemplateSourceActions.FILES_LIST,
    ).model_dump(by_alias=True),
    response_model=list[SshfsFilePublicSchema],
)
async def list_files(
    source_id: PyObjectId,
    service: Annotated[SshfsFileService, Depends(get_sshfs_file_service)],
) -> list[SshfsFilePublicSchema]:
    files = await service.get_list(
        query={'source_id': source_id}, skip=0, limit=0, projection_model=SshfsFilePublicSchema
    )
    return files


@router.delete(
    '/{source_id}/files/{file_id}',
    operation_id='delete_source_file',
    openapi_extra=GatewayEndpointConfig(
        policy='public',
        action=TemplateSourceActions.DELETE_USER_FILE,
    ).model_dump(by_alias=True),
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_source_file(
    source_id: PyObjectId,
    file_id: PyObjectId,
    service: Annotated[SshfsFileService, Depends(get_sshfs_file_service)],
) -> None:
    file = await service.get(query={'_id': file_id, 'source_id': source_id})
    if not file.file_type == SshfsFileType.USER:
        raise OnlyUserFilesCanBeDeletedException()

    await service.delete(query={'_id': file_id, 'source_id': source_id})
