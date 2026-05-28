import pathlib
from typing import Annotated
from uuid import uuid4

import anyio
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import HttpUrl

from saltbox_core.config import SETTINGS, logger
from saltbox_core.task_templates.schemas.source import TemplateSourceActions
from saltbox_core.task_templates.schemas.sshfs_file import (
    ManifestDigest,
    SshfsFileCreateSchema,
    SshfsFilePublicSchema,
    SshfsFileType,
    UnpackAs,
)
from saltbox_core.task_templates.services.sshfs_file import SshfsFileService, get_sshfs_file_service
from saltbox_core.task_templates.tiq_tasks import add_user_file_to_source_task
from saltbox_core.task_templates.utils.orchestrator import SyncOrchestrator, get_sync_orchestrator
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.discovery_client.schemas import GatewayEndpointConfig

router = APIRouter(prefix='/task-tpl-sources', tags=['Template Source Files'])


@router.post(
    '/{source_id}/files',
    operation_id='sshfs_file_add',
    openapi_extra=GatewayEndpointConfig(
        policy='public',
        action=TemplateSourceActions.ADD_USER_FILE,
    ).model_dump(by_alias=True),
    status_code=status.HTTP_202_ACCEPTED,
)
async def add_file_to_source(
    source_id: PyObjectId,
    rel_path: Annotated[str, Form(description='Destination path relative to sshfs root')],
    orchestrator: Annotated[SyncOrchestrator, Depends(get_sync_orchestrator)],
    file_service: Annotated[SshfsFileService, Depends(get_sshfs_file_service)],
    file: Annotated[UploadFile | None, File(description='File to upload')] = None,
    url: Annotated[str | None, Form(description='URL to download the file from')] = None,
    unpack_as: Annotated[
        UnpackAs | None,
        Form(description='Unpack as archive of specified format rather than place as is'),
    ] = None,
) -> str:
    if file is None and url is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail='Either file or url must be provided',
        )
    if file is not None and url is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail='Only one of file or url can be provided',
        )

    logger.debug('Url: %s', url)

    file_in = SshfsFileCreateSchema.model_validate(
        {
            'source_id': source_id,
            'file_type': SshfsFileType.USER,
            'rel_path': rel_path,
            'url': HttpUrl(url) if url is not None else None,
            'checksum': '',
            'checksum_type': ManifestDigest.SHA256,
            'token': None,
            'unpack_as': unpack_as,
        }
    )

    logger.debug('Creating SshfsFile with data: %s', file_in)
    file_id = await file_service.create(file_in)

    tmp_path: pathlib.Path | None = None
    if file is not None:
        content = await file.read()
        SETTINGS.sshfs_tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = SETTINGS.sshfs_tmp_dir / f'{uuid4()}.upload'
        logger.debug('Saving uploaded file to temporary path: %s', tmp_path)
        await anyio.Path(tmp_path).write_bytes(content)
        logger.debug('File exists on disk: %s', tmp_path.exists())
        await orchestrator.add_user_file(source_id, file_id, tmp_path=tmp_path)
        return str(file_id)
    task = await add_user_file_to_source_task.kiq(source_id=str(source_id), file_id=str(file_id), tmp_path=tmp_path)
    return task.task_id


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
    status_code=status.HTTP_202_ACCEPTED,
)
async def delete_source_file(
    source_id: PyObjectId,
    file_id: PyObjectId,
    service: Annotated[SshfsFileService, Depends(get_sshfs_file_service)],
) -> str:
    file = await service.get(query={'_id': file_id})
    if not file.file_type == SshfsFileType.USER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Only user files can be deleted',
        )

    await service.delete(query={'_id': file_id, 'source_id': source_id})
    return str(file_id)
