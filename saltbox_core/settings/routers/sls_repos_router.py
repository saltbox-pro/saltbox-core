from typing import Annotated

from fastapi import APIRouter, Body, Depends, Response, status

from saltbox_core.config import logger
from saltbox_core.db.schemas_base import TaskiqTaskIdResponse, TaskiqTaskResult
from saltbox_core.settings.schemas.sls_repos_schemas import (
    SettingsSlsActions,
    SettingsSlsRepoCreateSchema,
    SettingsSlsRepoListBody,
    SettingsSlsRepoModel,
    SettingsSlsRepoShortSchema,
    SettingsSlsRepoUpdateSchema,
)
from saltbox_core.settings.services.sls_repo_service import SettingsSlsRepoService, get_sls_repo_service
from saltbox_core.tasks.services.tasks_template import TaskTemplateService, get_task_template_service
from saltbox_core.tkq import broker
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.db.schemas_base import PaginatedResponse
from saltbox_sdk.discovery_client.schemas import GatewayEndpointConfig

router = APIRouter(prefix='/sls-repos', tags=['Settings'])


@router.post(
    '/list',
    operation_id='repo_list',
    openapi_extra=GatewayEndpointConfig(
        policy='core.git_repos.base',
        action=SettingsSlsActions.LIST,
    ).model_dump(by_alias=True),
)
async def sls_repo_settings_list(
    body: Annotated[SettingsSlsRepoListBody, Body()],
    service: Annotated[SettingsSlsRepoService, Depends(get_sls_repo_service)],
) -> PaginatedResponse[SettingsSlsRepoShortSchema]:
    return await service.get_list_paginated(
        query=body.query,
        skip=body.skip,
        limit=body.limit,
        projection_model=SettingsSlsRepoShortSchema,
        sort=body.sort,
    )


@router.post(
    '/sync_all',
    operation_id='repo_sync_all',
    openapi_extra=GatewayEndpointConfig(
        policy='core.git_repos.base',
        action=SettingsSlsActions.SYNC_ALL,
    ).model_dump(by_alias=True),
)
async def sls_repo_settings_sync_all(
    service: Annotated[SettingsSlsRepoService, Depends(get_sls_repo_service)],
) -> list[str]:
    return await service.sync_all()


# TODO: Deprecated, use /bg-task-result/{task_id} instead
@router.get(
    '/sync-status/{task_id}',
    operation_id='repo_sync_status',
    openapi_extra=GatewayEndpointConfig(
        policy='core.git_repos.base',
        action=SettingsSlsActions.SYNC_STATUS,
    ).model_dump(by_alias=True),
    deprecated=True,
)
async def get_sync_status(task_id: str) -> TaskiqTaskResult:
    """
    Get task status by task_id.
    """
    progress = await broker.result_backend.get_progress(task_id)

    logger.debug('Task progress: %s', progress)
    is_ready = await broker.result_backend.is_result_ready(task_id)
    if is_ready:
        result = await broker.result_backend.get_result(task_id)

        response = TaskiqTaskResult(
            task_id=task_id,
            progress=progress.state if progress else None,
            progress_meta=progress.meta if progress else None,
            return_value=result.return_value,
            is_err=result.is_err,
            execution_time=result.execution_time,
            log=result.log,
            error=result.error,
        )
    else:
        response = TaskiqTaskResult(
            task_id=task_id,
            progress=progress.state if progress else None,
            progress_meta=progress.meta if progress else None,
            return_value=None,
            is_err=False,
            execution_time=0,
            log='',
            error=None,
        )
    return response


@router.get(
    '/{sid}',
    operation_id='repo_get',
    openapi_extra=GatewayEndpointConfig(
        policy='core.git_repos.base',
        action=SettingsSlsActions.READ,
    ).model_dump(by_alias=True),
)
async def sls_repo_settings_retrieve(
    sid: PyObjectId,
    service: Annotated[SettingsSlsRepoService, Depends(get_sls_repo_service)],
) -> SettingsSlsRepoModel:
    return await service.get(sid)


@router.post(
    '',
    operation_id='repo_create',
    openapi_extra=GatewayEndpointConfig(
        policy='core.git_repos.base',
        action=SettingsSlsActions.CREATE,
    ).model_dump(by_alias=True),
)
async def sls_repo_settings_create(
    doc: SettingsSlsRepoCreateSchema,
    service: Annotated[SettingsSlsRepoService, Depends(get_sls_repo_service)],
) -> SettingsSlsRepoModel:
    obj_id = await service.create(doc)
    return await service.get(query=obj_id)


@router.put(
    '/{sid}',
    operation_id='repo_update',
    openapi_extra=GatewayEndpointConfig(
        policy='core.git_repos.base',
        action=SettingsSlsActions.UPDATE,
    ).model_dump(by_alias=True),
)
async def sls_repo_settings_update(
    sid: PyObjectId,
    doc: SettingsSlsRepoUpdateSchema,
    service: Annotated[SettingsSlsRepoService, Depends(get_sls_repo_service)],
) -> SettingsSlsRepoModel:
    obj_id = await service.update(sid, doc)
    return await service.get(query=obj_id)


@router.delete(
    '/{sid}',
    operation_id='repo_delete',
    openapi_extra=GatewayEndpointConfig(
        policy='core.git_repos.base',
        action=SettingsSlsActions.DELETE,
    ).model_dump(by_alias=True),
)
async def sls_repo_settings_delete(
    sid: PyObjectId,
    service: Annotated[SettingsSlsRepoService, Depends(get_sls_repo_service)],
    tpl_service: Annotated[TaskTemplateService, Depends(get_task_template_service)],
) -> Response:
    await service.delete_and_clean(sid, tpl_service)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    '/{sid}/sync',
    operation_id='repo_sync',
    openapi_extra=GatewayEndpointConfig(
        policy='core.git_repos.base',
        action=SettingsSlsActions.SYNC,
    ).model_dump(by_alias=True),
)
async def sls_repo_settings_sync(
    sid: PyObjectId,
    service: Annotated[SettingsSlsRepoService, Depends(get_sls_repo_service)],
) -> TaskiqTaskIdResponse:
    res = await service.sync(sid)
    return TaskiqTaskIdResponse(task_id=res)


@router.post(
    '/{sid}/activate',
    operation_id='repo_activate',
    openapi_extra=GatewayEndpointConfig(
        policy='core.git_repos.base',
        action=SettingsSlsActions.ACTIVATE,
    ).model_dump(by_alias=True),
)
async def sls_repo_settings_activate(
    sid: PyObjectId,
    service: Annotated[SettingsSlsRepoService, Depends(get_sls_repo_service)],
) -> SettingsSlsRepoModel:
    return await service.activate(sid)


@router.post(
    '/{sid}/deactivate',
    operation_id='repo_deactivate',
    openapi_extra=GatewayEndpointConfig(
        policy='core.git_repos.base',
        action=SettingsSlsActions.DEACTIVATE,
    ).model_dump(by_alias=True),
)
async def sls_repo_settings_deactivate(
    sid: PyObjectId,
    service: Annotated[SettingsSlsRepoService, Depends(get_sls_repo_service)],
) -> SettingsSlsRepoModel:
    return await service.deactivate(sid)
