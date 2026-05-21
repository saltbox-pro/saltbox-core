from typing import Annotated

from fastapi import APIRouter, Body, Depends, status

from saltbox_core.config import logger
from saltbox_core.task_templates.schemas.source import (
    TemplateSourceActions,
    TemplateSourceCreateSchema,
    TemplateSourceListBody,
    TemplateSourcePublicSchema,
    TemplateSourceUpdateSchema,
)
from saltbox_core.task_templates.schemas.sshfs_file import SshfsFileActions, SshfsFilePublicSchema
from saltbox_core.task_templates.services.source import TemplateSourceService, get_tpl_source_service
from saltbox_core.task_templates.services.sshfs_file import SshfsFileService, get_sshfs_file_service
from saltbox_core.task_templates.tiq_tasks import (
    source_discover_task,
    source_prepare_task,
    source_remove_task,
    source_sync_task,
)
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.db.schemas_base import PaginatedResponse
from saltbox_sdk.discovery_client.schemas import GatewayEndpointConfig

router = APIRouter(prefix='/task-tpl-sources', tags=['Task Template Sources'])


@router.post(
    '',
    operation_id='template_source_create',
    openapi_extra=GatewayEndpointConfig(
        policy='public',
        action=TemplateSourceActions.CREATE,
    ).model_dump(by_alias=True),
    status_code=status.HTTP_202_ACCEPTED,
    response_model=TemplateSourcePublicSchema,
)
async def source_create(
    source_in: TemplateSourceCreateSchema,
    service: Annotated[TemplateSourceService, Depends(get_tpl_source_service)],
) -> TemplateSourcePublicSchema:
    oid = await service.create(source_in)
    task = await source_discover_task.kiq(source_id=str(oid))
    logger.debug('Created task %s to discover source %s', task.task_id, oid)
    created = await service.get(oid, projection_model=TemplateSourcePublicSchema)
    return created


@router.post(
    '/list',
    operation_id='template_source_list',
    openapi_extra=GatewayEndpointConfig(
        policy='public',
        action=TemplateSourceActions.LIST,
    ).model_dump(by_alias=True),
    response_model=PaginatedResponse[TemplateSourcePublicSchema],
)
async def source_list(
    body: Annotated[TemplateSourceListBody, Body()],
    service: Annotated[TemplateSourceService, Depends(get_tpl_source_service)],
) -> PaginatedResponse[TemplateSourcePublicSchema]:
    sources = await service.get_list_paginated(
        query=body.query,
        skip=body.skip,
        limit=body.limit,
        projection_model=TemplateSourcePublicSchema,
        sort=body.sort,
    )
    return sources


@router.put(
    '/{source_id}',
    operation_id='template_source_update',
    openapi_extra=GatewayEndpointConfig(
        policy='public',
        action=TemplateSourceActions.UPDATE,
    ).model_dump(by_alias=True),
    response_model=TemplateSourcePublicSchema,
)
async def source_update(
    source_id: PyObjectId,
    source_in: TemplateSourceUpdateSchema,
    service: Annotated[TemplateSourceService, Depends(get_tpl_source_service)],
) -> TemplateSourcePublicSchema:
    await service.update(source_id, source_in)
    updated = await service.get(source_id, projection_model=TemplateSourcePublicSchema)
    return updated


@router.get(
    '/{source_id}/files',
    operation_id='sshfs_file_list',
    openapi_extra=GatewayEndpointConfig(
        policy='public',
        action=SshfsFileActions.LIST,
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


@router.get(
    '/{source_id}/discover',
    operation_id='template_source_discover',
    openapi_extra=GatewayEndpointConfig(
        policy='public',
        action=TemplateSourceActions.DISCOVER,
    ).model_dump(by_alias=True),
)
async def source_discover(source_id: PyObjectId) -> str:
    task = await source_discover_task.kiq(source_id=str(source_id))
    return task.task_id


@router.get(
    '/{source_id}/plug',
    operation_id='template_source_plug',
    openapi_extra=GatewayEndpointConfig(
        policy='public',
        action=TemplateSourceActions.PLUG,
    ).model_dump(by_alias=True),
)
async def source_plug(source_id: PyObjectId) -> str:
    task = await source_prepare_task.kiq(source_id=str(source_id))
    return task.task_id


@router.post(
    '/{source_id}/sync',
    operation_id='template_source_sync',
    openapi_extra=GatewayEndpointConfig(
        policy='public',
        action=TemplateSourceActions.SYNC,
    ).model_dump(by_alias=True),
)
async def source_sync(
    source_id: PyObjectId,
    master_ids: Annotated[list[PyObjectId], Body()],
) -> str:
    task = await source_sync_task.kiq(source_id=str(source_id), master_ids=[str(m_id) for m_id in master_ids])
    return task.task_id


@router.get(
    '/{source_id}',
    operation_id='template_source_get',
    openapi_extra=GatewayEndpointConfig(
        policy='public',
        action=TemplateSourceActions.READ,
    ).model_dump(by_alias=True),
    response_model=TemplateSourcePublicSchema,
)
async def source_get(
    source_id: PyObjectId,
    service: Annotated[TemplateSourceService, Depends(get_tpl_source_service)],
) -> TemplateSourcePublicSchema:
    source = await service.get(source_id, projection_model=TemplateSourcePublicSchema)
    return source


@router.delete(
    '/{source_id}',
    operation_id='template_source_delete',
    openapi_extra=GatewayEndpointConfig(
        policy='public',
        action=TemplateSourceActions.DELETE,
    ).model_dump(by_alias=True),
    status_code=status.HTTP_202_ACCEPTED,
)
async def source_delete(
    source_id: PyObjectId, service: Annotated[TemplateSourceService, Depends(get_tpl_source_service)]
) -> str:
    task = await source_remove_task.kiq(source_id=str(source_id))
    return task.task_id
