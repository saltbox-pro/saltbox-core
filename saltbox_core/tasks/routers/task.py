from typing import Annotated

from fastapi import APIRouter, Body, Depends

from saltbox_core.jobs.schemas.job_return_schemas import JobReturnListResponse, JobReturnsListBody
from saltbox_core.jobs.schemas.job_schemas import JobListBody, JobsListResponse
from saltbox_core.jobs.services.job_return_service import JobReturnService, get_job_return_service
from saltbox_core.jobs.services.job_services import JobService, get_job_service
from saltbox_core.minion_collections.schemas.filter_schemas import (
    FiltersActions,
    MinionFilterSchema,
)
from saltbox_core.tasks.schemas.task import (
    TaskCreateInputSchema,
    TaskCreateRequestSchema,
    TaskListBody,
    TaskListResponseSchema,
    TaskModel,
    TasksActions,
)
from saltbox_core.tasks.schemas.tasks_minion import TaskMinionListBody, TaskMinionModel
from saltbox_core.tasks.schemas.tasks_status import TaskStatusListBody, TaskStatusModel
from saltbox_core.tasks.services.task import TaskService, get_task_service
from saltbox_core.tasks.services.tasks_lifespan import TaskLifespanService, get_task_lifespan_service
from saltbox_core.tasks.services.tasks_minion import TaskMinionService, get_task_minion_service
from saltbox_core.tasks.services.tasks_status import TaskStatusService, get_task_status_service
from saltbox_core.utilities.model_schema import get_model_schema
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.db.schemas_base import PaginatedResponse, Source, UserShort
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
async def tasks_list(
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
                'source': Source.model_validate({'type': 'rest', 'id': user.sub}),
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


@router.post(
    '/{tid}/statuses',
    operation_id='tasks_statuses',
    openapi_extra=GatewayEndpointConfig(
        policy='core.tasks.list',
        action=TasksActions.LIST,
    ).model_dump(by_alias=True),
)
async def task_statuses(
    tid: PyObjectId,
    body: Annotated[TaskStatusListBody, Body()],
    task_status_service: Annotated[TaskStatusService, Depends(get_task_status_service)],
) -> PaginatedResponse[TaskStatusModel]:
    query = {'$and': [{'task_id': tid}, body.query]}

    task_statuses_list = await task_status_service.get_list_paginated(
        query=query,
        limit=body.limit,
        skip=body.skip,
        projection_model=TaskStatusModel,
        sort=body.sort,
    )

    return task_statuses_list


@router.post(
    '/{tid}/minions',
    operation_id='tasks_minions',
    openapi_extra=GatewayEndpointConfig(
        policy='core.tasks.list',
        action=TasksActions.LIST,
    ).model_dump(by_alias=True),
)
async def task_minions(
    tid: PyObjectId,
    body: Annotated[TaskMinionListBody, Body()],
    task_minion_service: Annotated[TaskMinionService, Depends(get_task_minion_service)],
) -> PaginatedResponse[TaskMinionModel]:
    query = {'$and': [{'task_id': tid}, body.query]}

    task_minions_list = await task_minion_service.get_list_paginated(
        query=query,
        limit=body.limit,
        skip=body.skip,
        projection_model=TaskMinionModel,
        sort=body.sort,
    )

    return task_minions_list


@router.post(
    '/{tid}/jobs',
    operation_id='task_jobs',
    deprecated=True,
    openapi_extra=GatewayEndpointConfig(
        policy='core.tasks.read',
        action=TasksActions.READ,
    ).model_dump(by_alias=True),
)
async def task_jobs(
    tid: PyObjectId,
    body: Annotated[JobListBody, Body()],
    job_service: Annotated[JobService, Depends(get_job_service)],
) -> PaginatedResponse[JobsListResponse]:
    query = {'$and': [{'source.type': 'task', 'source.id': str(tid)}, body.query]}

    task_jobs_list = await job_service.get_list_paginated(
        query=query,
        limit=body.limit,
        skip=body.skip,
        projection_model=JobsListResponse,
        sort=body.sort,
    )

    return task_jobs_list


@router.post(
    '/{tid}/returns',
    operation_id='task_returns',
    deprecated=True,
    openapi_extra=GatewayEndpointConfig(
        policy='core.tasks.read',
        action=TasksActions.READ,
    ).model_dump(by_alias=True),
)
async def task_returns(
    tid: PyObjectId,
    body: Annotated[JobReturnsListBody, Body()],
    job_return_service: Annotated[JobReturnService, Depends(get_job_return_service)],
) -> PaginatedResponse[JobReturnListResponse]:
    query = {'$and': [{'source.type': 'task', 'source.id': str(tid)}, body.query]}

    task_jobs_returns_list = await job_return_service.get_list_paginated(
        query=query,
        limit=body.limit,
        skip=body.skip,
        projection_model=JobReturnListResponse,
        sort=body.sort,
    )

    return task_jobs_returns_list


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
    await task_lifespan_service.run()

    return await task_lifespan_service.get_task()


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
    await task_lifespan_service.stop()

    return await task_lifespan_service.get_task()


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
    await task_lifespan_service.restart_failed()

    return await task_lifespan_service.get_task()


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
    await task_lifespan_service.restart_failed_on_minion(master=master, minion_id=minion_id)

    return await task_lifespan_service.get_task()
