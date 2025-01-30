import logging.config
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, WebSocket, status

from fastms_core import http_errors
from fastms_core.config import LOG_CONFIG
from fastms_core.db.mongo.schemas_base import PaginatedResponse
from fastms_core.db.redis import RedisDependency
from fastms_core.jobs.exceptions import JobDoesNotExistsException
from fastms_core.jobs.schemas import Job, JobResult
from fastms_core.jobs.services import JobServiceDependency
from fastms_core.tasks.schemas import (
    TaskCreateFromTemplateSchema,
    TaskListQueryParams,
    TaskListResponseSchema,
    TaskSchema,
    TaskTemplateCreateSchema,
    TaskTemplateListQueryParams,
    TaskTemplateListSchema,
    TaskTemplateSchema,
    TaskTemplateUpdateSchema,
)
from fastms_core.tasks.services import (
    TaskServiceDependency,
    TaskServiceLifespanDependency,
    TaskTemplateServiceDependency,
)
from fastms_core.utilities.exceptions import ObjectDoesNotExistError
from fastms_core.utilities.jid import JID
from fastms_core.utilities.websocket import PubSubAuthenticatedWebSocket

logging.config.dictConfig(LOG_CONFIG.model_dump())

logger = logging.getLogger(__name__)


router = APIRouter(
    prefix='/tasks',
    tags=['Tasks'],
    responses={status.HTTP_404_NOT_FOUND: {'description': 'Not found'}},
)

ws_router = APIRouter(prefix='/tasks')


# Task templates views


@router.get('/template', operation_id='templates_list')
async def templates_list(
    params: Annotated[TaskTemplateListQueryParams, Query()], task_templates_service: TaskTemplateServiceDependency
) -> PaginatedResponse[TaskTemplateListSchema]:
    task_templates: PaginatedResponse[TaskTemplateListSchema] = await task_templates_service.get_list_paginated(
        page=params.page, per_page=params.per_page, projection_schema=TaskTemplateListSchema
    )

    return task_templates


@router.post('/template', operation_id='template_create')
async def template_create(
        item: TaskTemplateCreateSchema, task_templates_service: TaskTemplateServiceDependency
) -> TaskTemplateSchema:
    obj: TaskTemplateSchema = await task_templates_service.create_obj(
        obj_data=item, projection_schema=TaskTemplateSchema
    )

    return obj


@router.get('/template/{tid}', operation_id='template_retrieve')
async def template_retrieve(
        tid: str, task_templates_service: TaskTemplateServiceDependency
) -> TaskTemplateSchema:
    try:
        obj: TaskTemplateSchema = await task_templates_service.get_obj(
            obj_id=tid, projection_schema=TaskTemplateSchema
        )
    except ObjectDoesNotExistError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task template does not found') from e

    return obj


@router.put('/template/{tid}', operation_id='template_update')
async def template_update(
        tid: str, item: TaskTemplateUpdateSchema, task_templates_service: TaskTemplateServiceDependency
) -> TaskTemplateSchema:
    try:
        updated_obj: TaskTemplateSchema = task_templates_service.update_obj(
            obj_id=tid, obj_data=item, projection_schema=TaskTemplateSchema
        )
    except ObjectDoesNotExistError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task template does not found') from e

    return updated_obj


@router.delete('/template/{tid}', operation_id='template_delete', status_code=status.HTTP_204_NO_CONTENT)
async def template_delete(tid: str, task_templates_service: TaskTemplateServiceDependency) -> Response:
    deleted_count = await task_templates_service.delete_obj(id=tid)

    return Response(status_code=status.HTTP_204_NO_CONTENT, content=deleted_count)


# Tasks views


@router.get('', operation_id='tasks_list')
async def tasks_list(
        params: Annotated[TaskListQueryParams, Query()], task_service: TaskServiceDependency
) -> PaginatedResponse[TaskListResponseSchema]:
    task_list: PaginatedResponse[TaskListResponseSchema] = await task_service.get_list_paginated(
        page=params.page, per_page=params.per_page, projection_schema=TaskListResponseSchema
    )

    return task_list


@router.post('', operation_id='task_create')
async def task_create(item: TaskCreateFromTemplateSchema, task_service: TaskServiceDependency) -> TaskSchema:
    try:
        task: TaskSchema = await task_service.create_obj(obj_data=item)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    return task


@router.get('/{tid}', operation_id='task_retrieve')
async def task_retrieve(tid: str, task_service: TaskServiceDependency) -> TaskSchema:
    try:
        task: TaskSchema = await task_service.get_obj(obj_id=tid, projection_schema=TaskSchema)
    except ObjectDoesNotExistError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task does not found') from e

    return task


@router.get('/{tid}/jobs', operation_id='task_jobs')
async def task_jobs(
        tid: str,
        task_service: TaskServiceDependency,
        job_service: JobServiceDependency
) -> list[Job]:
    result: list[Job] = []

    try:
        task: TaskSchema = await task_service.get_obj(obj_id=tid)

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
        tid: str,
        task_service: TaskServiceDependency,
        job_service: JobServiceDependency
) -> list[JobResult]:
    result: list[JobResult] = []

    try:
        task: TaskSchema = await task_service.get_obj(obj_id=tid, projection_schema=TaskSchema)

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
async def task_run(task_lifespan_service: TaskServiceLifespanDependency) -> TaskSchema:
    try:
        task: TaskSchema = await task_lifespan_service.get_task()
    except ObjectDoesNotExistError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task not found') from e

    await task_lifespan_service.run()

    return task


@router.post('/{tid}/stop', operation_id='task_stop')
async def task_stop(task_lifespan_service: TaskServiceLifespanDependency) -> TaskSchema:
    try:
        task: TaskSchema = await task_lifespan_service.get_task()
    except ObjectDoesNotExistError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task not found') from e

    await task_lifespan_service.stop()

    return task


@ws_router.websocket('')
async def tasks_websocket(websocket: WebSocket, rdb: RedisDependency) -> None:
    secure_websocket = PubSubAuthenticatedWebSocket(websocket, rdb)
    await secure_websocket.handle_pubsub({
        'task:*:create': TaskSchema,
        'task:*:update': TaskSchema,
    })


@ws_router.websocket('/{tid}')
async def task_websocket(
    tid: str,
    websocket: WebSocket,
    rdb: RedisDependency,
    task_service: TaskServiceDependency
) -> None:
    task: TaskSchema = await task_service.get_obj(obj_id=tid, projection_schema=TaskSchema)

    if not task:
        msg = f'Task not found by ID={tid}'
        raise http_errors.WebSocketPolicyViolation(msg)

    def job_new_handler(data) -> str:
        return Job(**{
            'status': Job.JobStatus.started,
            **data
        }).model_dump_json(by_alias=True)

    secure_websocket = PubSubAuthenticatedWebSocket(websocket, rdb)
    await secure_websocket.handle_pubsub({
        f'task:{tid}:job:*:return': JobResult,
        f'task:{tid}:job:*:new': job_new_handler,
        f'task:{tid}:update': TaskSchema,
    })
