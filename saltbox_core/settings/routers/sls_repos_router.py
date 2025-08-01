from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from saltbox_core.config import logger
from saltbox_core.db.schemas_base import TaskiqTaskIdResponse, TaskiqTaskResult
from saltbox_core.settings.schemas.sls_repos_schemas import (
    SettingsSlsRepoCreateSchema,
    SettingsSlsRepoModel,
    SettingsSlsRepoShortSchema,
    SettingsSlsRepoUpdateSchema,
)
from saltbox_core.settings.services.sls_repo_service import SettingsSlsRepoService, get_sls_repo_service
from saltbox_core.tasks.services.tasks_templates import TaskTemplateService, get_task_template_service
from saltbox_core.tkq import broker
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.db.schemas_base import PaginatedResponse, SkipLimitParams

router = APIRouter(prefix='/sls-repos', tags=['Settings'])


@router.get('')
async def sls_repo_settings_list(
    params: Annotated[SkipLimitParams, Query()],
    service: Annotated[SettingsSlsRepoService, Depends(get_sls_repo_service)],
) -> PaginatedResponse[SettingsSlsRepoShortSchema]:
    return await service.get_list_paginated(
        query=None, skip=params.skip, limit=params.limit, projection_model=SettingsSlsRepoShortSchema
    )


@router.post('/sync_all')
async def sls_repo_settings_sync_all(
    service: Annotated[SettingsSlsRepoService, Depends(get_sls_repo_service)],
) -> list[str]:
    return await service.sync_all()


@router.get('/sync-status/{task_id}')
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


@router.get('/{sid}')
async def sls_repo_settings_retrieve(
    sid: PyObjectId,
    service: Annotated[SettingsSlsRepoService, Depends(get_sls_repo_service)],
) -> SettingsSlsRepoModel:
    return await service.get(sid)


@router.post('')
async def sls_repo_settings_create(
    doc: SettingsSlsRepoCreateSchema,
    service: Annotated[SettingsSlsRepoService, Depends(get_sls_repo_service)],
) -> SettingsSlsRepoModel:
    return await service.create(doc)


@router.put('/{sid}')
async def sls_repo_settings_update(
    sid: PyObjectId,
    doc: SettingsSlsRepoUpdateSchema,
    service: Annotated[SettingsSlsRepoService, Depends(get_sls_repo_service)],
) -> SettingsSlsRepoModel:
    return await service.update(sid, doc)


@router.delete('/{sid}')
async def sls_repo_settings_delete(
    sid: PyObjectId,
    service: Annotated[SettingsSlsRepoService, Depends(get_sls_repo_service)],
    tpl_service: Annotated[TaskTemplateService, Depends(get_task_template_service)],
) -> Response:
    await service.delete_and_clean(sid, tpl_service)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post('/{sid}/sync')
async def sls_repo_settings_sync(
    sid: PyObjectId,
    service: Annotated[SettingsSlsRepoService, Depends(get_sls_repo_service)],
) -> TaskiqTaskIdResponse:
    res = await service.sync(sid)
    return TaskiqTaskIdResponse(task_id=res)


@router.post('/{sid}/activate')
async def sls_repo_settings_activate(
    sid: PyObjectId,
    service: Annotated[SettingsSlsRepoService, Depends(get_sls_repo_service)],
) -> SettingsSlsRepoModel:
    return await service.activate(sid)


@router.post('/{sid}/deactivate')
async def sls_repo_settings_deactivate(
    sid: PyObjectId,
    service: Annotated[SettingsSlsRepoService, Depends(get_sls_repo_service)],
) -> SettingsSlsRepoModel:
    return await service.deactivate(sid)
