from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, status

from saltbox_core.jobs.exceptions import JobDoesNotExistsException
from saltbox_core.jobs.schemas.job_schemas import JobModel, JobResult
from saltbox_core.jobs.services.job_services import JobServiceDependency
from saltbox_core.minion_collections.schemas.collection_schemas import CollectionModel
from saltbox_core.minion_collections.services.collection_service import CollectionService, get_collection_service
from saltbox_core.tasks.schemas.task_schemas import (
    TaskCreateInputSchema,
    TaskCreateRequestSchema,
    TaskListQueryParams,
    TaskListResponseSchema,
    TaskModel,
)
from saltbox_core.tasks.services.tasks import TaskService, get_task_service
from saltbox_core.tasks.services.tasks_lifespan import TaskLifespanService, get_task_lifespan_service
from saltbox_core.utilities.exceptions import ServiceError
from saltbox_core.utilities.jid import JID
from saltbox_core.utilities.websocket import PubSubAuthenticatedWebSocket
from saltbox_sdk import http_errors
from saltbox_sdk.db.exceptions import ObjectNotFoundError
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.db.redis.config import RedisDependency
from saltbox_sdk.db.schemas_base import PaginatedResponse

router = APIRouter(
    prefix='/tasks',
    tags=['Tasks'],
    responses={status.HTTP_404_NOT_FOUND: {'description': 'Not found'}},
)

ws_router = APIRouter(prefix='/tasks')


@router.get('', operation_id='tasks_list')
async def tasks_list(
    params: Annotated[TaskListQueryParams, Query()],
    task_service: Annotated[TaskService, Depends(get_task_service)],
    collection_service: Annotated[CollectionService, Depends(get_collection_service)],
) -> PaginatedResponse[TaskListResponseSchema]:
    try:
        collection: CollectionModel = await collection_service.get_by_slug(params.collection_slug)
    except ObjectNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Collection does not exists') from e

    task_list: PaginatedResponse[TaskListResponseSchema] = await task_service.get_list_paginated(
        query={'target_collection.id': PyObjectId(collection.id)},
        limit=params.limit,
        skip=params.skip,
        projection_model=TaskListResponseSchema,
    )

    return task_list


@router.post('', operation_id='task_create')
async def task_create(
    item: TaskCreateRequestSchema,
    task_service: Annotated[TaskService, Depends(get_task_service)],
) -> TaskModel:
    # TODO (i.moshkov): remove this
    if item.query == {'$and': [{'$expr': True}]}:
        item.query = {}

    create_data = TaskCreateInputSchema(**item.model_dump(by_alias=True))

    try:
        task: TaskModel = await task_service.create(data=create_data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except ServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except ObjectNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

    return task


@router.get('/{tid}', operation_id='task_retrieve')
async def task_retrieve(
    tid: PyObjectId,
    task_service: Annotated[TaskService, Depends(get_task_service)],
) -> TaskModel:
    try:
        task: TaskModel = await task_service.get(query=tid)
    except ObjectNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task does not found') from e

    return task


@router.get('/{tid}/jobs', operation_id='task_jobs')
async def task_jobs(
    tid: PyObjectId,
    task_service: Annotated[TaskService, Depends(get_task_service)],
    job_service: JobServiceDependency,
) -> list[JobModel]:
    result: list[JobModel] = []

    try:
        task: TaskModel = await task_service.get(query=tid)

        for task_job in task.jobs.values():
            try:
                job = await job_service.get_job(JID(task_job.jid))
                result.append(job)
            except JobDoesNotExistsException:
                continue
    except ObjectNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task does not found') from e

    return result


@router.get('/{tid}/returns', operation_id='task_returns')
async def task_returns(
    tid: PyObjectId,
    task_service: Annotated[TaskService, Depends(get_task_service)],
    job_service: JobServiceDependency,
) -> list[JobResult]:
    result: list[JobResult] = []

    try:
        task: TaskModel = await task_service.get(query=tid)

        for task_job in task.jobs.values():
            try:
                job_returns: list[JobResult] = await job_service.get_job_all_returns(JID(task_job.jid))
                result.extend(job_returns)
            except JobDoesNotExistsException:
                continue
    except ObjectNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task does not found') from e

    return result


@router.post('/{tid}/run', operation_id='task_run')
async def task_run(
    task_lifespan_service: Annotated[TaskLifespanService, Depends(get_task_lifespan_service)],
) -> TaskModel:
    try:
        task: TaskModel = await task_lifespan_service.get_task()
    except ObjectNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task not found') from e

    await task_lifespan_service.run()

    return task


@router.post('/{tid}/stop', operation_id='task_stop')
async def task_stop(
    task_lifespan_service: Annotated[TaskLifespanService, Depends(get_task_lifespan_service)],
) -> TaskModel:
    try:
        task: TaskModel = await task_lifespan_service.get_task()
    except ObjectNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task not found') from e

    await task_lifespan_service.stop()

    return task


@router.post('/{tid}/restart_failed', operation_id='restart_failed')
async def restart_failed(
    task_lifespan_service: Annotated[TaskLifespanService, Depends(get_task_lifespan_service)],
) -> TaskModel:
    try:
        task: TaskModel = await task_lifespan_service.get_task()
    except ObjectNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task not found') from e

    await task_lifespan_service.restart_failed()

    return task


@router.post('/{tid}/restart_failed_on_minion', operation_id='restart_failed_on_minion')
async def restart_failed_on_minion(
    master: str,
    minion_id: str,
    task_lifespan_service: Annotated[TaskLifespanService, Depends(get_task_lifespan_service)],
) -> TaskModel:
    try:
        task: TaskModel = await task_lifespan_service.get_task()
    except ObjectNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task not found') from e

    await task_lifespan_service.restart_failed_on_minion(master=master, minion_id=minion_id)

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
        return JobModel(**{'status': JobModel.JobStatus.started, **data}).model_dump_json(by_alias=True)

    secure_websocket = PubSubAuthenticatedWebSocket(websocket, rdb)
    await secure_websocket.handle_pubsub(
        {
            f'task:{tid}:job:*:return': JobResult,
            f'task:{tid}:job:*:new': job_new_handler,
            f'task:{tid}:update': TaskModel,
        }
    )
