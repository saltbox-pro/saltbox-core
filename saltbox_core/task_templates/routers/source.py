from typing import Annotated

from fastapi import APIRouter, Body, Depends, File, Form, UploadFile, status

from saltbox_core.db.schemas_base import TaskiqTaskIdResponse
from saltbox_core.task_templates.exceptions import ArchiveUnpackException
from saltbox_core.task_templates.schemas.source import (
    SourceListWithExtrasSchema,
    TemplateSourceActions,
    TemplateSourceCreateLocalSchema,
    TemplateSourceImportFromGitSchema,
    TemplateSourceListBody,
    TemplateSourcePublicSchema,
    TemplateSourceUpdateSchema,
)
from saltbox_core.task_templates.services.source import TemplateSourceService, get_tpl_source_service
from saltbox_core.task_templates.tiq_tasks import (
    source_check_external_list_task,
    source_discover_task,
    source_prepare_task,
    source_remove_task,
    source_sync_task,
    source_unplug_task,
)
from saltbox_core.task_templates.utils.orchestrator import SyncOrchestrator, get_sync_orchestrator
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.db.schemas_base import PaginatedResponse
from saltbox_sdk.discovery_client.schemas import GatewayEndpointConfig

router = APIRouter(prefix='/task-template-sources', tags=['Task Templates / Sources'])


# CRUD
@router.post(
    '',
    operation_id='template_source_create_local',
    openapi_extra=GatewayEndpointConfig(
        policy='public',
        action=TemplateSourceActions.CREATE,
    ).model_dump(by_alias=True),
    status_code=status.HTTP_202_ACCEPTED,
    response_model=TaskiqTaskIdResponse,
)
async def source_create_local(
    source_in: TemplateSourceCreateLocalSchema,
    service: Annotated[TemplateSourceService, Depends(get_tpl_source_service)],
) -> TaskiqTaskIdResponse:
    oid = await service.create_local(source_in)
    task = await source_discover_task.kiq(source_id=str(oid))
    return TaskiqTaskIdResponse(task_id=task.task_id)


@router.get(
    '/{source_id}',
    operation_id='template_source_get',
    openapi_extra=GatewayEndpointConfig(
        policy='public',
        action=TemplateSourceActions.READ,
    ).model_dump(by_alias=True),
    response_model=SourceListWithExtrasSchema,
)
async def source_get(
    source_id: PyObjectId,
    service: Annotated[TemplateSourceService, Depends(get_tpl_source_service)],
) -> SourceListWithExtrasSchema:
    source = await service.get(source_id, projection_model=SourceListWithExtrasSchema)
    return source


@router.post(
    '/list',
    operation_id='template_source_list',
    openapi_extra=GatewayEndpointConfig(
        policy='public',
        action=TemplateSourceActions.LIST,
    ).model_dump(by_alias=True),
    response_model=PaginatedResponse[SourceListWithExtrasSchema],
)
async def source_list(
    body: Annotated[TemplateSourceListBody, Body()],
    service: Annotated[TemplateSourceService, Depends(get_tpl_source_service)],
) -> PaginatedResponse[SourceListWithExtrasSchema]:
    sources = await service.get_list_paginated(
        query=body.query,
        skip=body.skip,
        limit=body.limit,
        projection_model=SourceListWithExtrasSchema,
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


@router.delete(
    '/{source_id}',
    operation_id='template_source_delete',
    openapi_extra=GatewayEndpointConfig(
        policy='public',
        action=TemplateSourceActions.DELETE,
    ).model_dump(by_alias=True),
    status_code=status.HTTP_202_ACCEPTED,
    response_model=TaskiqTaskIdResponse,
)
async def source_delete(
    source_id: PyObjectId, service: Annotated[TemplateSourceService, Depends(get_tpl_source_service)]
) -> TaskiqTaskIdResponse:
    task = await source_remove_task.kiq(source_id=str(source_id))
    return TaskiqTaskIdResponse(task_id=task.task_id)


# Imports
@router.post(
    '/imports/archive',
    operation_id='template_source_import_from_archive',
    openapi_extra=GatewayEndpointConfig(
        policy='public',
        action=TemplateSourceActions.CREATE,
    ).model_dump(by_alias=True),
    status_code=status.HTTP_202_ACCEPTED,
    response_model=TaskiqTaskIdResponse,
)
async def source_import_from_archive(
    name: Annotated[str, Form(description='Name of the template source')],
    file: Annotated[UploadFile, File(description='Archive to upload')],
    service: Annotated[TemplateSourceService, Depends(get_tpl_source_service)],
    orchestrator: Annotated[SyncOrchestrator, Depends(get_sync_orchestrator)],
    description: Annotated[str, Form(description='Description of the template source')] = '',
    namespace: Annotated[str, Form(description='Namespace for the template source')] = '',
) -> TaskiqTaskIdResponse:
    oid = await service.create_from_archive(name=name, description=description, namespace=namespace)

    created = await service.get(oid, projection_model=TemplateSourcePublicSchema)
    try:
        await orchestrator.save_and_unpack_archive(file, local_path=created.local_path)
    except Exception as e:
        await service.delete(oid)
        raise ArchiveUnpackException(detail=str(e)) from None

    task = await source_discover_task.kiq(source_id=str(oid))

    return TaskiqTaskIdResponse(task_id=task.task_id)


@router.post(
    '/imports/git',
    operation_id='template_source_import_from_git',
    openapi_extra=GatewayEndpointConfig(
        policy='public',
        action=TemplateSourceActions.CREATE,
    ).model_dump(by_alias=True),
    status_code=status.HTTP_202_ACCEPTED,
    response_model=TaskiqTaskIdResponse,
)
async def source_import_from_git(
    source_in: TemplateSourceImportFromGitSchema,
    service: Annotated[TemplateSourceService, Depends(get_tpl_source_service)],
) -> TaskiqTaskIdResponse:
    oid = await service.create_from_url(source_in)
    task = await source_discover_task.kiq(source_id=str(oid))
    return TaskiqTaskIdResponse(task_id=task.task_id)


# Actions
@router.get(
    '/actions/check-external-list',
    operation_id='template_source_check_external_list',
    openapi_extra=GatewayEndpointConfig(
        policy='public',
        action=TemplateSourceActions.CHECK_EXTERNAL_LIST,
    ).model_dump(by_alias=True),
    status_code=status.HTTP_202_ACCEPTED,
    response_model=TaskiqTaskIdResponse,
)
async def source_check_external_list() -> TaskiqTaskIdResponse:
    task = await source_check_external_list_task.kiq()
    return TaskiqTaskIdResponse(task_id=task.task_id)


@router.get(
    '/{source_id}/actions/discover',
    operation_id='template_source_action_discover',
    openapi_extra=GatewayEndpointConfig(
        policy='public',
        action=TemplateSourceActions.DISCOVER,
    ).model_dump(by_alias=True),
    status_code=status.HTTP_202_ACCEPTED,
    response_model=TaskiqTaskIdResponse,
)
async def source_action_discover(source_id: PyObjectId) -> TaskiqTaskIdResponse:
    task = await source_discover_task.kiq(source_id=str(source_id))
    return TaskiqTaskIdResponse(task_id=task.task_id)


@router.get(
    '/{source_id}/actions/plug',
    operation_id='template_source_action_plug',
    openapi_extra=GatewayEndpointConfig(
        policy='public',
        action=TemplateSourceActions.PLUG,
    ).model_dump(by_alias=True),
    status_code=status.HTTP_202_ACCEPTED,
    response_model=TaskiqTaskIdResponse,
)
async def source_action_plug(source_id: PyObjectId) -> TaskiqTaskIdResponse:
    task = await source_prepare_task.kiq(source_id=str(source_id))
    return TaskiqTaskIdResponse(task_id=task.task_id)


@router.get(
    '/{source_id}/actions/unplug',
    operation_id='template_source_action_unplug',
    openapi_extra=GatewayEndpointConfig(
        policy='public',
        action=TemplateSourceActions.UNPLUG,
    ).model_dump(by_alias=True),
    status_code=status.HTTP_202_ACCEPTED,
    response_model=TaskiqTaskIdResponse,
)
async def source_action_unplug(source_id: PyObjectId) -> TaskiqTaskIdResponse:
    task = await source_unplug_task.kiq(source_id=str(source_id))
    return TaskiqTaskIdResponse(task_id=task.task_id)


@router.post(
    '/{source_id}/actions/sync',
    operation_id='template_source_action_sync',
    openapi_extra=GatewayEndpointConfig(
        policy='public',
        action=TemplateSourceActions.SYNC,
    ).model_dump(by_alias=True),
    status_code=status.HTTP_202_ACCEPTED,
    response_model=TaskiqTaskIdResponse,
)
async def source_action_sync(source_id: PyObjectId) -> TaskiqTaskIdResponse:
    task = await source_sync_task.kiq(source_id=str(source_id))
    return TaskiqTaskIdResponse(task_id=task.task_id)
