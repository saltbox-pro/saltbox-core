from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from salt_box_core.celery import celery
from salt_box_core.config import logger
from salt_box_core.db.exceptions import DuplicateKeyError, ObjectNotFoundError
from salt_box_core.db.mongo.schemas_base import (
    CeleryTaskIdResponse,
    CeleryTaskStatus,
    PaginatedResponse,
    SkipLimitParams,
)
from salt_box_core.jobs.schemas.job_sc_schemas import JobSchemaModel, JobSchemaShortSchema
from salt_box_core.jobs.services.job_sc_service import JobSchemaService, get_job_schema_service

router = APIRouter(prefix='/job-schemas', tags=['Job Schemas'])


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
) -> CeleryTaskIdResponse:
    try:
        res = await service.sync()
        return CeleryTaskIdResponse(task_id=res)
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
async def get_sync_status(task_id: str) -> CeleryTaskStatus:
    task_result = celery.AsyncResult(task_id)

    return CeleryTaskStatus(
        task_id=task_result.id,
        status=task_result.status,
        result=str(task_result.result),
        date_done=task_result.date_done,
        children=[str(child) for child in task_result.children] if task_result.children else [],
    )


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
