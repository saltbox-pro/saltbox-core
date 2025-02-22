import logging.config
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, status

from salt_box_core import http_errors
from salt_box_core.config import LOG_CONFIG
from salt_box_core.db.mongo.schemas_base import PaginatedResponse, PyObjectId
from salt_box_core.db.redis import RedisDependency
from salt_box_core.jobs.exceptions import JobDoesNotExistsException
from salt_box_core.jobs.schemas import Job, JobResult
from salt_box_core.jobs.services import JobServiceDependency
from salt_box_core.tasks.schemas.task_schemas import (
    TaskCreateFromTemplateSchema,
    TaskListQueryParams,
    TaskListResponseSchema,
    TaskModel,
)
from salt_box_core.tasks.services.tasks import TaskService, get_task_service
from salt_box_core.tasks.services.tasks_lifespan import TaskLifespanService, get_task_lifespan_service
from salt_box_core.utilities.exceptions import ObjectDoesNotExistError
from salt_box_core.utilities.jid import JID
from salt_box_core.utilities.websocket import PubSubAuthenticatedWebSocket

logging.config.dictConfig(LOG_CONFIG.model_dump())

logger = logging.getLogger(__name__)


router = APIRouter(
    prefix='/tasks',
    tags=['Tasks'],
    responses={status.HTTP_404_NOT_FOUND: {'description': 'Not found'}},
)

ws_router = APIRouter(prefix='/tasks')


@router.get('', operation_id='tasks_list')
async def tasks_list(
    params: Annotated[TaskListQueryParams, Query()], task_service: Annotated[TaskService, Depends(get_task_service)]
) -> PaginatedResponse[TaskListResponseSchema]:
    task_list: PaginatedResponse[TaskListResponseSchema] = await task_service.get_list_paginated(
        query={}, limit=params.per_page, skip=params.page * params.per_page, projection_model=TaskListResponseSchema
    )

    return task_list


@router.post('', operation_id='task_create')
async def task_create(
    item: TaskCreateFromTemplateSchema, task_service: Annotated[TaskService, Depends(get_task_service)]
) -> TaskModel:
    try:
        task: TaskModel = await task_service.create(data=item)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    return task


@router.get('/{tid}', operation_id='task_retrieve')
async def task_retrieve(tid: PyObjectId, task_service: Annotated[TaskService, Depends(get_task_service)]) -> TaskModel:
    try:
        task: TaskModel = await task_service.get(query=tid)
    except ObjectDoesNotExistError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task does not found') from e

    return task


@router.get('/{tid}/jobs', operation_id='task_jobs')
async def task_jobs(
    tid: PyObjectId, task_service: Annotated[TaskService, Depends(get_task_service)], job_service: JobServiceDependency
) -> list[Job]:
    result: list[Job] = []

    try:
        task: TaskModel = await task_service.get(query=tid)

        for task_job in task.jobs:
            try:
                job = await job_service.get_job(JID(task_job.jid))
                result.append(job)
            except JobDoesNotExistsException:
                continue
    except ObjectDoesNotExistError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task does not found') from e

    return result


@router.get('/{tid}/returns', operation_id='task_returns')
async def task_returns(
    tid: PyObjectId, task_service: Annotated[TaskService, Depends(get_task_service)], job_service: JobServiceDependency
) -> list[JobResult]:
    result: list[JobResult] = []

    try:
        task: TaskModel = await task_service.get(query=tid)

        for task_job in task.jobs:
            try:
                job_returns: list[JobResult] = await job_service.get_job_all_returns(JID(task_job.jid))
                result.extend(job_returns)
            except JobDoesNotExistsException:
                continue
    except ObjectDoesNotExistError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task does not found') from e

    return result


@router.post('/{tid}/run', operation_id='task_run')
async def task_run(
    task_lifespan_service: Annotated[TaskLifespanService, Depends(get_task_lifespan_service)],
) -> TaskModel:
    try:
        task: TaskModel = await task_lifespan_service.get_task()
    except ObjectDoesNotExistError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task not found') from e

    await task_lifespan_service.run()

    return task


@router.post('/{tid}/stop', operation_id='task_stop')
async def task_stop(
    task_lifespan_service: Annotated[TaskLifespanService, Depends(get_task_lifespan_service)],
) -> TaskModel:
    try:
        task: TaskModel = await task_lifespan_service.get_task()
    except ObjectDoesNotExistError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task not found') from e

    await task_lifespan_service.stop()

    return task


@ws_router.websocket('')
async def tasks_websocket(websocket: WebSocket, rdb: RedisDependency) -> None:
    secure_websocket = PubSubAuthenticatedWebSocket(websocket, rdb)
    await secure_websocket.handle_pubsub(
        {
            'task:*:create': TaskModel,
            'task:*:update': TaskModel,
        }
    )


@ws_router.websocket('/{tid}')
async def task_websocket(
    tid: PyObjectId,
    websocket: WebSocket,
    rdb: RedisDependency,
    task_service: Annotated[TaskService, Depends(get_task_service)],
) -> None:
    task: TaskModel = await task_service.get(query=tid)

    if not task:
        msg = f'Task not found by ID={tid}'
        raise http_errors.WebSocketPolicyViolation(msg)

    def job_new_handler(data: dict) -> str:
        return Job(**{'status': Job.JobStatus.started, **data}).model_dump_json(by_alias=True)

    secure_websocket = PubSubAuthenticatedWebSocket(websocket, rdb)
    await secure_websocket.handle_pubsub(
        {
            f'task:{tid}:job:*:return': JobResult,
            f'task:{tid}:job:*:new': job_new_handler,
            f'task:{tid}:update': TaskModel,
        }
    )
