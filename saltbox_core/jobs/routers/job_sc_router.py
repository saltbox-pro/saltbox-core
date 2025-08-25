from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from saltbox_core.config import logger
from saltbox_core.db.schemas_base import TaskiqTaskIdResponse, TaskiqTaskResult
from saltbox_core.jobs.schemas.job_sc_schemas import JobSchemaModel, JobSchemasActions, JobSchemaShortSchema
from saltbox_core.jobs.services.job_sc_service import JobSchemaService, get_job_schema_service
from saltbox_core.tkq import broker
from saltbox_sdk.db.schemas_base import PaginatedResponse, SkipLimitParams
from saltbox_sdk.discovery_client.schemas import GatewayEndpointConfig
from saltbox_sdk.fastapi_utils.dependencies import get_opa_query

router = APIRouter(prefix='/json-schemas', tags=['JSON Schemas'])


@router.get(
    '',
    operation_id='jobs_schemas_list',
    openapi_extra=GatewayEndpointConfig(
        policy='core.jobs.schemas.list',
        action=JobSchemasActions.LIST,
    ).model_dump(by_alias=True),
)
async def get_json_schemas_list(
    params: Annotated[SkipLimitParams, Query()],
    opa_query: Annotated[dict, Depends(get_opa_query)],
    service: Annotated[JobSchemaService, Depends(get_job_schema_service)],
) -> PaginatedResponse[JobSchemaShortSchema]:
    logger.info(f'OPA query: {opa_query}')

    return await service.get_list_paginated(
        query=opa_query, skip=params.skip, limit=params.limit, projection_model=JobSchemaShortSchema
    )


@router.get(
    '/clean',
    operation_id='jobs_schemas_clean',
    openapi_extra=GatewayEndpointConfig(
        policy='core.jobs.schemas.base',
        action=JobSchemasActions.CLEAN,
    ).model_dump(by_alias=True),
    status_code=status.HTTP_204_NO_CONTENT,
)
async def clean_schemas(
    service: Annotated[JobSchemaService, Depends(get_job_schema_service)],
) -> None:
    await service.remove_repo_data()
    await service.delete_many({})


@router.post(
    '/sync',
    operation_id='jobs_schemas_sync',
    openapi_extra=GatewayEndpointConfig(
        policy='core.jobs.schemas.base',
        action=JobSchemasActions.SYNC,
    ).model_dump(by_alias=True),
)
async def sync_schemas(
    service: Annotated[JobSchemaService, Depends(get_job_schema_service)],
) -> TaskiqTaskIdResponse:
    res = await service.sync()
    return TaskiqTaskIdResponse(task_id=res)


@router.get(
    '/sync-status/{task_id}',
    operation_id='jobs_schemas_sync_status',
    openapi_extra=GatewayEndpointConfig(
        policy='core.jobs.schemas.base',
        action=JobSchemasActions.SYNC,
    ).model_dump(by_alias=True),
)
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


@router.get(
    '/{name}',
    operation_id='jobs_schemas_get',
    openapi_extra=GatewayEndpointConfig(
        policy='core.jobs.schemas.read',
        action=JobSchemasActions.READ,
    ).model_dump(by_alias=True),
)
async def get_json_schema(
    name: str,
    service: Annotated[JobSchemaService, Depends(get_job_schema_service)],
) -> JobSchemaModel:
    if await service.exists({'name': name}):
        return await service.get_by_name(name)
    # Try get default schema
    return await service.get_by_name('default')
