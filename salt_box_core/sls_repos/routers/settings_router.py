from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from salt_box_core.config import logger
from salt_box_core.db.exceptions import DuplicateKeyError, ObjectNotFoundError
from salt_box_core.db.mongo.schemas_base import PaginatedResponse, PyObjectId, SkipLimitParams
from salt_box_core.schema_sync.schemas import JSONSchemaSyncResponse
from salt_box_core.sls_repos.schemas.settings_schemas import (
    SettingsSlsRepoCreateSchema,
    SettingsSlsRepoModel,
    SettingsSlsRepoShortSchema,
    SettingsSlsRepoUpdateSchema,
)
from salt_box_core.sls_repos.services.sls_repo_service import SettingsSlsRepoService, get_sls_repo_service
from salt_box_core.tasks.services.tasks_templates import TaskTemplateService, get_task_template_service

router = APIRouter(prefix='/sls-repos', tags=['Settings'])


@router.get('')
async def sls_repo_settings_list(
    params: Annotated[SkipLimitParams, Query()],
    service: Annotated[SettingsSlsRepoService, Depends(get_sls_repo_service)],
) -> PaginatedResponse[SettingsSlsRepoShortSchema]:
    try:
        return await service.get_list_paginated(
            query=None, skip=params.skip, limit=params.limit, projection_model=SettingsSlsRepoShortSchema
        )
    except Exception as e:
        logger.error('Error: %s', e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Something went wrong... See logs'
        ) from e


@router.post('/sync_all')
async def sls_repo_settings_sync_all(
    service: Annotated[SettingsSlsRepoService, Depends(get_sls_repo_service)],
) -> None:
    try:
        await service.sync_all()
    except Exception as e:
        logger.error('Error: %s', e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f'Something went wrong...: {e!s}'
        ) from e


@router.get('/{sid}')
async def sls_repo_settings_retrieve(
    sid: PyObjectId,
    service: Annotated[SettingsSlsRepoService, Depends(get_sls_repo_service)],
) -> SettingsSlsRepoModel:
    try:
        return await service.get(sid)
    except ObjectNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f'Repository with id {sid} not found') from e


@router.post('')
async def sls_repo_settings_create(
    doc: SettingsSlsRepoCreateSchema,
    service: Annotated[SettingsSlsRepoService, Depends(get_sls_repo_service)],
) -> SettingsSlsRepoModel:
    try:
        return await service.create(doc)
    except DuplicateKeyError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f'Repository with url {doc.repo_url} already exists'
        ) from e
    except Exception as e:
        logger.error('Error: %s', e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f'Something went wrong...: {e!s}'
        ) from e


@router.put('/{sid}')
async def sls_repo_settings_update(
    sid: PyObjectId,
    doc: SettingsSlsRepoUpdateSchema,
    service: Annotated[SettingsSlsRepoService, Depends(get_sls_repo_service)],
) -> SettingsSlsRepoModel:
    try:
        return await service.update(sid, doc)
    except Exception as e:
        msg = f'Error while updating repository: {e!s}'
        logger.error(msg)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=msg) from e


@router.delete('/{sid}')
async def sls_repo_settings_delete(
    sid: PyObjectId,
    service: Annotated[SettingsSlsRepoService, Depends(get_sls_repo_service)],
    tpl_service: Annotated[TaskTemplateService, Depends(get_task_template_service)],
) -> Response:
    try:
        await service.delete_and_clean(sid, tpl_service)
    except Exception as e:
        msg = f'Error while deleting repository: {e!s}'
        logger.error(msg)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=msg) from e
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post('/{sid}/sync')
async def sls_repo_settings_sync(
    sid: PyObjectId,
    service: Annotated[SettingsSlsRepoService, Depends(get_sls_repo_service)],
    tpl_service: Annotated[TaskTemplateService, Depends(get_task_template_service)],
) -> JSONSchemaSyncResponse:
    try:
        return await service.sync(sid, tpl_service)
    except Exception as e:
        logger.error('Error: %s', e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f'Something went wrong...: {e!s}'
        ) from e


@router.post('/{sid}/activate')
async def sls_repo_settings_activate(
    sid: PyObjectId,
    service: Annotated[SettingsSlsRepoService, Depends(get_sls_repo_service)],
) -> SettingsSlsRepoModel:
    try:
        return await service.activate(sid)
    except Exception as e:
        logger.error('Error: %s', e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f'Something went wrong...: {e!s}'
        ) from e


@router.post('/{sid}/deactivate')
async def sls_repo_settings_deactivate(
    sid: PyObjectId,
    service: Annotated[SettingsSlsRepoService, Depends(get_sls_repo_service)],
) -> SettingsSlsRepoModel:
    try:
        return await service.deactivate(sid)
    except Exception as e:
        logger.error('Error: %s', e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f'Something went wrong...: {e!s}'
        ) from e
