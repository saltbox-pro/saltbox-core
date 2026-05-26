from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends

from saltbox_core.jobs.schemas.job_return_schemas import JobReturnModel
from saltbox_core.jobs.schemas.job_schemas import JobListBody, JobsListResponse
from saltbox_core.jobs.services.job_return_service import JobReturnService, get_job_return_service
from saltbox_core.jobs.services.job_services import JobService, get_job_service
from saltbox_core.minion_collections.schemas.filter import FiltersActions, MinionFilterSchema
from saltbox_core.tasks.schemas.task import (
    RestartFailedBody,
    TaskCreateInputSchema,
    TaskCreateRequestSchema,
    TaskListBody,
    TaskListResponseSchema,
    TaskModel,
    TasksActions,
)
from saltbox_core.tasks.schemas.tasks_minion import (
    TaskMinionListBody,
    TaskMinionListResponse,
    TaskMinionStatus,
    TaskMinionTgtOnlySchema,
)
from saltbox_core.tasks.schemas.tasks_status import TaskStatusListBody, TaskStatusModel
from saltbox_core.tasks.services.task import TaskService, get_task_service
from saltbox_core.tasks.services.tasks_lifespan import TaskLifespanService, get_task_lifespan_service
from saltbox_core.tasks.services.tasks_minion import TaskMinionService, get_task_minion_service
from saltbox_core.tasks.services.tasks_status import TaskStatusService, get_task_status_service
from saltbox_core.utilities.model_schema import get_model_schema
from saltbox_sdk.db.mongo.schemas_base import EmptyModel, PyObjectId
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
    obj_id = await task_service.create(
        data=TaskCreateInputSchema.model_validate(
            {
                'user': user.model_dump(),
                'source': Source.model_validate({'type': 'rest', 'id': user.sub}),
                **item.model_dump(by_alias=True),
            }
        )
    )
    return await task_service.get(query=obj_id)


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
async def task_minions_list(
    tid: PyObjectId,
    body: Annotated[TaskMinionListBody, Body()],
    task_minion_service: Annotated[TaskMinionService, Depends(get_task_minion_service)],
) -> PaginatedResponse[TaskMinionListResponse]:
    query = {'$and': [{'task_id': tid}, body.query]}

    result = await task_minion_service.get_list_paginated(
        query=query,
        limit=body.limit,
        skip=body.skip,
        projection_model=TaskMinionListResponse,
        sort=body.sort,
    )

    return result


@router.post(
    '/{tid}/jobs',
    operation_id='task_jobs',
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


@router.get(
    '/{tid}/jobs/returns',
    operation_id='task_jobs_returns',
    openapi_extra=GatewayEndpointConfig(
        policy='core.tasks.read',
        action=TasksActions.READ,
    ).model_dump(by_alias=True),
)
async def task_return_data(
    tid: PyObjectId,
    task_minion_mongo_id: PyObjectId,
    opa_query: Annotated[dict, Depends(get_opa_query)],
    task_minion_service: Annotated[TaskMinionService, Depends(get_task_minion_service)],
    job_return_service: Annotated[JobReturnService, Depends(get_job_return_service)],
) -> list[JobReturnModel]:
    task_minion = await task_minion_service.get(
        query={'_id': task_minion_mongo_id, 'task_id': tid}, projection_model=TaskMinionTgtOnlySchema
    )

    query: dict[str, Any] = {
        'source.type': 'task',
        'source.id': str(tid),
        'salt_master': task_minion.master,
        'minion_id': task_minion.minion_id,
    }

    if opa_query:
        query = {'$and': [query, opa_query]}

    return await job_return_service.get_list(query=query, projection_model=JobReturnModel)


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

    return await task_lifespan_service.get_full_task()


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

    return await task_lifespan_service.get_full_task()


@router.post(
    '/{tid}/restart_failed',
    operation_id='restart_failed',
    openapi_extra=GatewayEndpointConfig(
        policy='core.tasks.run',
        action=TasksActions.RUN,
    ).model_dump(by_alias=True),
)
async def restart_failed(
    tid: PyObjectId,
    body: Annotated[RestartFailedBody, Body()],
    task_minion_service: Annotated[TaskMinionService, Depends(get_task_minion_service)],
    task_lifespan_service: Annotated[TaskLifespanService, Depends(get_task_lifespan_service)],
) -> TaskModel:
    query: dict[str, Any] = {'task_id': tid, 'status': TaskMinionStatus.failed}
    subqueries: list[dict] = []

    if body.minions_by_tgt:
        subqueries.append(
            {
                '$or': [
                    {'minion_id': minion_tgt.minion_id, 'master': minion_tgt.salt_master}
                    for minion_tgt in body.minions_by_tgt
                ]
            }
        )
    if body.minions_by_ids:
        subqueries.append({'minion_inner_id': {'$in': body.minions_by_ids}})

    if subqueries:
        query['$and'] = subqueries

    task_minions = await task_minion_service.get_list(query=query, projection_model=EmptyModel)

    await task_lifespan_service.restart_on_minions(minions_ids=[minion.id for minion in task_minions])

    return await task_lifespan_service.get_full_task()
