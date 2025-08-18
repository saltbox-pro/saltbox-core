from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from saltbox_core.config import logger
from saltbox_core.jobs.exceptions import JobDoesNotExistsException
from saltbox_core.jobs.schemas.job_schemas import JobModel, JobResult
from saltbox_core.jobs.services.job_services import JobService, get_job_service
from saltbox_core.minion_collections.services.collection_service import CollectionService, get_collection_service
from saltbox_core.tasks.schemas.task_schemas import (
    TaskCreateInputSchema,
    TaskCreateRequestSchema,
    TaskListQueryParams,
    TaskListResponseSchema,
    TaskModel,
    TasksActions,
)
from saltbox_core.tasks.services.tasks import TaskService, get_task_service
from saltbox_core.tasks.services.tasks_lifespan import TaskLifespanService, get_task_lifespan_service
from saltbox_core.utilities.jid import JID
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.db.schemas_base import PaginatedResponse, UserShort
from saltbox_sdk.discovery_client.schemas import GatewayEndpointConfig
from saltbox_sdk.fastapi_utils.dependencies import get_current_user, get_opa_query

router = APIRouter(prefix='/tasks', tags=['Tasks'])


@router.get(
    '',
    operation_id='tasks_list',
    openapi_extra=GatewayEndpointConfig(
        policy='core.tasks.list',
        action=TasksActions.LIST,
    ).model_dump(by_alias=True),
)
async def tasks_list(
    params: Annotated[TaskListQueryParams, Query()],
    opa_query: Annotated[dict, Depends(get_opa_query)],
    task_service: Annotated[TaskService, Depends(get_task_service)],
    collection_service: Annotated[CollectionService, Depends(get_collection_service)],
) -> PaginatedResponse[TaskListResponseSchema]:
    logger.info(f'OPA query: {opa_query}')

    collection = await collection_service.get_by_slug(params.collection_slug)
    query = {'target_collection.id': PyObjectId(collection.id)}
    if opa_query:
        query.update(opa_query)
    task_list = await task_service.get_list_paginated(
        query=query,
        limit=params.limit,
        skip=params.skip,
        projection_model=TaskListResponseSchema,
    )

    return task_list


@router.post(
    '',
    operation_id='task_create',
    openapi_extra=GatewayEndpointConfig(
        policy='core.tasks.create',
        action=TasksActions.CREATE,
    ).model_dump(by_alias=True),
)
async def task_create(
    request: Request,
    item: TaskCreateRequestSchema,
    user: Annotated[UserShort, Depends(get_current_user)],
    task_service: Annotated[TaskService, Depends(get_task_service)],
) -> TaskModel:
    # TODO (i.moshkov): remove this
    if item.query == {'$and': [{'$expr': True}]}:
        item.query = {}

    logger.debug(f'User {user}')

    create_data = TaskCreateInputSchema(**{'user': user.model_dump(), **item.model_dump(by_alias=True)})
    return await task_service.create(data=create_data)


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
            job = await job_service.get_job(JID(task_job.jid))
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
    job_service: Annotated[JobService, Depends(get_job_service)],
) -> list[JobResult]:
    result: list[JobResult] = []

    task = await task_service.get(query=tid)

    for task_job in task.jobs.values():
        try:
            job_returns = await job_service.get_job_all_returns(JID(task_job.jid))
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
