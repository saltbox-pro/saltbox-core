from typing import Annotated

from fastapi import APIRouter, Body, Depends

# from saltbox_core.config import logger
from saltbox_core.jobs.exceptions import JobDoesNotExistsException
from saltbox_core.jobs.schemas.job_return_schemas import JobReturnModel
from saltbox_core.jobs.schemas.job_schemas import JobModel
from saltbox_core.jobs.services.job_return_service import JobReturnService, get_job_return_service
from saltbox_core.jobs.services.job_services import JobService, get_job_service
from saltbox_core.minion_collections.schemas.filter_schemas import (
    FiltersActions,
    MinionFilterSchema,
)
from saltbox_core.tasks.schemas.task_schemas import (
    TaskCreateInputSchema,
    TaskCreateRequestSchema,
    TaskListBody,
    TaskListResponseSchema,
    TaskModel,
    TasksActions,
    TaskSource,
)
from saltbox_core.tasks.services.tasks import TaskService, get_task_service
from saltbox_core.tasks.services.tasks_lifespan import TaskLifespanService, get_task_lifespan_service
from saltbox_core.utilities.model_schema import get_model_schema
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.db.schemas_base import PaginatedResponse, UserShort
from saltbox_sdk.discovery_client.schemas import GatewayEndpointConfig
from saltbox_sdk.fastapi_utils.dependencies import get_current_user, get_opa_query

router = APIRouter(prefix='/tasks', tags=['Tasks'])


@router.post(
    '/list',
    operation_id='tasks_list',
    openapi_extra=GatewayEndpointConfig(
        policy='core.tasks.list',
        action=TasksActions.LIST,
    ).model_dump(by_alias=True),
)
async def tasks_list_new(
    opa_query: Annotated[dict, Depends(get_opa_query)],
    body: Annotated[TaskListBody, Body()],
    task_service: Annotated[TaskService, Depends(get_task_service)],
) -> PaginatedResponse[TaskListResponseSchema]:
    query = body.query
    if opa_query:
        query = {'$and': [query, opa_query]}

    task_list = await task_service.get_list_paginated(
        query=query,
        limit=body.limit,
        skip=body.skip,
        projection_model=TaskListResponseSchema,
        sort=body.sort,
    )

    return task_list


@router.get(
    '/filter-schema',
    operation_id='tasks_filter_schema',
    openapi_extra=GatewayEndpointConfig(
        policy='core.tasks.list',
        action=FiltersActions.GET_SCHEMA,
    ).model_dump(by_alias=True),
)
async def filter_schema() -> list[MinionFilterSchema]:
    return [MinionFilterSchema(**field) for field in get_model_schema(TaskModel)]


@router.post(
    '',
    operation_id='task_create',
    openapi_extra=GatewayEndpointConfig(
        policy='core.tasks.create',
        action=TasksActions.CREATE,
    ).model_dump(by_alias=True),
)
async def task_create(
    item: TaskCreateRequestSchema,
    user: Annotated[UserShort, Depends(get_current_user)],
    task_service: Annotated[TaskService, Depends(get_task_service)],
) -> TaskModel:
    return await task_service.create(
        data=TaskCreateInputSchema(
            **{
                'user': user.model_dump(),
                'source': TaskSource.model_validate({'type': 'rest', 'id': user.sub}),
                **item.model_dump(by_alias=True),
            }
        )
    )


@router.get(
    '/{tid}',
    operation_id='task_retrieve',
    openapi_extra=GatewayEndpointConfig(
        policy='core.tasks.read',
        action=TasksActions.READ,
    ).model_dump(by_alias=True),
)
async def task_retrieve(
    tid: PyObjectId,
    task_service: Annotated[TaskService, Depends(get_task_service)],
) -> TaskModel:
    return await task_service.get(query=tid)


@router.get(
    '/{tid}/jobs',
    operation_id='task_jobs',
    openapi_extra=GatewayEndpointConfig(
        policy='core.tasks.read',
        action=TasksActions.READ,
    ).model_dump(by_alias=True),
)
async def task_jobs(
    tid: PyObjectId,
    task_service: Annotated[TaskService, Depends(get_task_service)],
    job_service: Annotated[JobService, Depends(get_job_service)],
) -> list[JobModel]:
    result: list[JobModel] = []
    task = await task_service.get(query=tid)

    for task_job in task.jobs.values():
        try:
            job = await job_service.get(query={'jid': task_job.jid, 'salt_master': task_job.target.master})
            result.append(job)
        except JobDoesNotExistsException:
            continue
    return result


@router.get(
    '/{tid}/returns',
    operation_id='task_returns',
    openapi_extra=GatewayEndpointConfig(
        policy='core.tasks.read',
        action=TasksActions.READ,
    ).model_dump(by_alias=True),
)
async def task_returns(
    tid: PyObjectId,
    task_service: Annotated[TaskService, Depends(get_task_service)],
    job_return_service: Annotated[JobReturnService, Depends(get_job_return_service)],
) -> list[JobReturnModel]:
    result: list[JobReturnModel] = []

    task = await task_service.get(query=tid)

    for task_job in task.jobs.values():
        try:
            job_returns = await job_return_service.get_list(
                query={'jid': task_job.jid, 'salt_master': task_job.target.master}
            )
            result.extend(job_returns)
        except JobDoesNotExistsException:
            continue
    return result


@router.post(
    '/{tid}/run',
    operation_id='task_run',
    openapi_extra=GatewayEndpointConfig(
        policy='core.tasks.run',
        action=TasksActions.RUN,
    ).model_dump(by_alias=True),
)
async def task_run(
    task_lifespan_service: Annotated[TaskLifespanService, Depends(get_task_lifespan_service)],
) -> TaskModel:
    task = await task_lifespan_service.get_task()
    await task_lifespan_service.run()
    return task


@router.post(
    '/{tid}/stop',
    operation_id='task_stop',
    openapi_extra=GatewayEndpointConfig(
        policy='core.tasks.run',
        action=TasksActions.RUN,
    ).model_dump(by_alias=True),
)
async def task_stop(
    task_lifespan_service: Annotated[TaskLifespanService, Depends(get_task_lifespan_service)],
) -> TaskModel:
    task = await task_lifespan_service.get_task()
    await task_lifespan_service.stop()

    return task


@router.post(
    '/{tid}/restart_failed',
    operation_id='restart_failed',
    openapi_extra=GatewayEndpointConfig(
        policy='core.tasks.run',
        action=TasksActions.RUN,
    ).model_dump(by_alias=True),
)
async def restart_failed(
    task_lifespan_service: Annotated[TaskLifespanService, Depends(get_task_lifespan_service)],
) -> TaskModel:
    task = await task_lifespan_service.get_task()
    await task_lifespan_service.restart_failed()

    return task


@router.post(
    '/{tid}/restart_failed_on_minion',
    operation_id='restart_failed_on_minion',
    openapi_extra=GatewayEndpointConfig(
        policy='core.tasks.run',
        action=TasksActions.RUN,
    ).model_dump(by_alias=True),
)
async def restart_failed_on_minion(
    master: str,
    minion_id: str,
    task_lifespan_service: Annotated[TaskLifespanService, Depends(get_task_lifespan_service)],
) -> TaskModel:
    task = await task_lifespan_service.get_task()
    await task_lifespan_service.restart_failed_on_minion(master=master, minion_id=minion_id)

    return task
