import logging.config
from typing import Annotated

import pydantic
from fastapi import APIRouter, Query, WebSocket
from pydantic import Field, ValidationError

from salt_box_core import http_errors
from salt_box_core.config import LOG_CONFIG, SETTINGS
from salt_box_core.db.redis.config import RedisDependency
from salt_box_core.db.schemas_base import CursoredResponse, PaginatedResponse
from salt_box_core.event_bus.masters_bus import send_message_and_wait_response_to_master
from salt_box_core.jobs.exceptions import (
    JobCreateException,
    JobDoesNotExistsException,
    JobServiceException,
    JobServiceInvalidArgsException,
)
from salt_box_core.jobs.schemas.event_bus_schemas import CreateJobMessage, JobSyncMessage
from salt_box_core.jobs.schemas.job_schemas import (
    CreateJobRequest,
    GetJobReturnResponse,
    IntJid,
    JobCreateSchema,
    JobModel,
    JobResult,
    JobsListCursorRequest,
    JobsListRequest,
    JobsListResponse,
    JobSyncResponse,
)
from salt_box_core.jobs.services.job_services import JobServiceDependency
from salt_box_core.utilities.jid import JID
from salt_box_core.utilities.websocket import PubSubAuthenticatedWebSocket

logging.config.dictConfig(LOG_CONFIG.model_dump())

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix='/jobs',
    tags=['Jobs'],
    responses={404: {'description': 'Not found'}},
)

ws_router = APIRouter(prefix='/jobs')


@router.get('/cursored_list', operation_id='jobs_list_cursor')
async def jobs_list_cursor(
    request: Annotated[JobsListCursorRequest, Query()],
    job_service: JobServiceDependency,
) -> CursoredResponse[JobsListResponse]:
    matches = []

    if request.fun:
        matches.append(f'"fun": "{request.fun}"')

    if request.minion:
        matches.append(rf'"minions": \[*"{request.minion}"*\]')

    return await job_service.get_list_cursored_by_dt(
        start_datetime=request.start_datetime,
        end_datetime=request.end_datetime,
        cursor=request.cursor or 0,
        count=request.count,
        match='*' + '*'.join(matches) + '*',
        projection_model=JobsListResponse,
    )


@router.get('', operation_id='jobs_list')
async def jobs_list(
    request: Annotated[JobsListRequest, Query()],
    job_service: JobServiceDependency,
) -> PaginatedResponse[JobModel]:
    try:
        jobs: PaginatedResponse[JobModel] = await job_service.get_list_by_dt_paginated(
            start_datetime=request.start_datetime,
            end_datetime=request.end_datetime,
            skip=request.skip,
            limit=request.limit,
        )
        return jobs
    except ValidationError as err:
        raise http_errors.InternalServerError(detail=err.errors()) from err
    except JobServiceInvalidArgsException as err:
        raise http_errors.BadRequest(str(err)) from err


@router.get('/{jid}', operation_id='job_retrieve')
async def job_retrieve(
    jid: IntJid,
    job_service: JobServiceDependency,
) -> JobModel:
    _jid = JID(jid)

    try:
        job: JobModel = await job_service.get_job(_jid)
        return job
    except ValidationError as e:
        raise http_errors.InternalServerError(detail=e.errors()) from e
    except JobDoesNotExistsException as e:
        raise http_errors.NotFound(detail=str(e)) from e


@router.post('', operation_id='job_create')
async def job_create(
    item: CreateJobRequest,
    job_service: JobServiceDependency,
) -> JobModel:
    try:
        return await job_service.create(
            JobCreateSchema.model_validate(
                {
                    **item.model_dump(by_alias=True),
                }
            )
        )
    except JobCreateException as error:
        raise http_errors.BadRequest(detail=str(error)) from error


@router.post('/sync_run', operation_id='job_create_sync')
async def job_create_sync(
    item: CreateJobRequest,
) -> JobSyncResponse:
    try:
        job_res: JobSyncMessage = JobSyncMessage(
            **await send_message_and_wait_response_to_master(
                message=CreateJobMessage(
                    tgt=item.tgt,
                    tgt_type=item.tgt_type,
                    fun=item.fun,
                    master=item.salt_master,
                    arg=item.data.data_args or [] if item.data else [],
                    kwarg=item.data.data_kwargs or {} if item.data else {},
                ),
                message_tag='run_job_sync',
                response_timeout=10.0,
            )
        )

        return JobSyncResponse(**job_res.model_dump())
    except JobCreateException as error:
        raise http_errors.BadRequest(detail=str(error)) from error


@router.get('/{jid}/returns-count', operation_id='job_returns_count')
async def job_returns_count(
    jid: IntJid,
    job_service: JobServiceDependency,
) -> Annotated[int, Field(ge=0)]:
    """
    How many return data records for job at the moment.

    To be used in pair with GET /jobs/{jid}/return cycle.
    """
    return await job_service.get_job_returns_count(JID(jid))


@router.get('/{jid}/return', operation_id='job_returns_list')
async def job_returns_list(
    jid: IntJid,
    job_service: JobServiceDependency,
    count: Annotated[int, Field(gt=0, lt=SETTINGS.max_count)] = 10,
    cursor: pydantic.NonNegativeInt = 0,
) -> GetJobReturnResponse:
    """
    Get list of returned by minions data.

    Amount is not guaranteed to be exactly count.
    """

    try:
        job_returns, next_cursor = await job_service.get_job_returns(jid=JID(jid), count=count, cursor=cursor)
    except JobServiceException as e:
        raise http_errors.InternalServerError(detail=str(e)) from e

    return GetJobReturnResponse(cursor=next_cursor, result=job_returns, length=len(job_returns))


@ws_router.websocket('')
async def jobs_rets_websocket(websocket: WebSocket, rdb: RedisDependency) -> None:
    def job_new_handler(data: dict) -> str:
        return JobModel(**{'status': JobModel.JobStatus.started, **data}).model_dump_json(by_alias=True)

    secure_websocket = PubSubAuthenticatedWebSocket(websocket, rdb)
    await secure_websocket.handle_pubsub({'job:*:new': job_new_handler})


@ws_router.websocket('/{jid}/return')
async def jobs_endpoint_websocket(
    jid: IntJid,
    job_service: JobServiceDependency,
    websocket: WebSocket,
    rdb: RedisDependency,
) -> None:
    _jid = JID(jid)

    try:
        await job_service.get_job(_jid)
    except JobDoesNotExistsException as e:
        msg = f'Job not found by JID={jid}'
        raise http_errors.WebSocketPolicyViolation(msg) from e

    secure_websocket = PubSubAuthenticatedWebSocket(websocket, rdb)
    await secure_websocket.handle_pubsub({f'job:{jid}:return': JobResult})
