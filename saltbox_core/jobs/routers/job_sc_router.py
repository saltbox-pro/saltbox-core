from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from saltbox_core.config import logger
from saltbox_core.db.schemas_base import TaskiqTaskIdResponse, TaskiqTaskResult
from saltbox_core.jobs.schemas.job_sc_schemas import JobSchemaModel, JobSchemaShortSchema
from saltbox_core.jobs.services.job_sc_service import JobSchemaService, get_job_schema_service
from saltbox_core.tkq import broker
from saltbox_sdk.db.exceptions import DuplicateKeyError, ObjectNotFoundError
from saltbox_sdk.db.schemas_base import PaginatedResponse, SkipLimitParams

router = APIRouter(prefix='/json-schemas', tags=['JSON Schemas'])


@router.get('')
async def get_json_schemas_list(
    params: Annotated[SkipLimitParams, Query()],
    service: Annotated[JobSchemaService, Depends(get_job_schema_service)],
) -> PaginatedResponse[JobSchemaShortSchema]:
    try:
        return await service.get_list_paginated(
            query=None, skip=params.skip, limit=params.limit, projection_model=JobSchemaShortSchema
        )
    except Exception as e:
        logger.error('Error: %s', e)
        raise HTTPException(status_code=500, detail='Something went wrong... See logs') from e


@router.get('/clean', status_code=status.HTTP_204_NO_CONTENT)
async def clean_schemas(
    service: Annotated[JobSchemaService, Depends(get_job_schema_service)],
) -> None:
    try:
        await service.remove_repo_data()
        await service.delete_many({})
    except Exception as e:
        msg = f'Error while cleaning schemas: {e!s}'
        logger.error(msg)
        raise HTTPException(status_code=500, detail=msg) from e


@router.post('/sync')
async def sync_schemas(
    service: Annotated[JobSchemaService, Depends(get_job_schema_service)],
) -> TaskiqTaskIdResponse:
    try:
        res = await service.sync()
        return TaskiqTaskIdResponse(task_id=res)
    except DuplicateKeyError as e:
        logger.error('Error: %s', e)
        raise HTTPException(status_code=409, detail=f'{e!s}') from e
    except TimeoutError as e:
        logger.error('Error: %s', e)
        raise HTTPException(status_code=408, detail=f'{e!s}') from e
    except Exception as e:
        logger.error('Error: %s', e)
        raise HTTPException(status_code=500, detail=f'Something went wrong...: {e!s}') from e


@router.get('/sync-status/{task_id}')
async def get_sync_status(task_id: str) -> TaskiqTaskResult:
    """
    Get task status by task_id.
    """
    progress = await broker.result_backend.get_progress(task_id)

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


@router.get('/{name}')
async def get_json_schema(
    name: str,
    service: Annotated[JobSchemaService, Depends(get_job_schema_service)],
) -> JobSchemaModel:
    if await service.exists({'name': name}):
        return await service.get_by_name(name)
    # Try get default schema
    try:
        return await service.get_by_name('default')
    except ObjectNotFoundError:
        msg = f'Schema with name `{name}` not found. Default schema also not found: check schema repository'
        logger.error(msg)
        raise HTTPException(status_code=404, detail=msg) from None
