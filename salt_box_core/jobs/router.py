import datetime
import logging.config
from typing import Annotated

import pydantic
from fastapi import APIRouter, WebSocket
from pydantic import Field, ValidationError

from salt_box_core import http_errors
from salt_box_core.config import LOG_CONFIG, SETTINGS
from salt_box_core.db.redis import RedisDependency
from salt_box_core.jobs.exceptions import (
    JobCreateException,
    JobDoesNotExistsException,
    JobServiceException,
    JobServiceInvalidArgsException,
)
from salt_box_core.jobs.schemas import (
    CreateJobRequest,
    CreateJobResponse,
    GetJobReturnResponse,
    IntJid,
    Job,
    JobCreate,
    JobResult,
)
from salt_box_core.jobs.services import JobServiceDependency
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


@router.get('', operation_id='jobs_list')
async def jobs_list(
    job_service: JobServiceDependency,
    start_datetime: pydantic.PastDatetime,
    end_datetime: datetime.datetime | None = None,
) -> list[Job]:
    try:
        jobs: list[Job] = await job_service.get_jobs(start_datetime=start_datetime, end_datetime=end_datetime)
        return jobs
    except ValidationError as err:
        raise http_errors.InternalServerError(detail=err.errors()) from err
    except JobServiceInvalidArgsException as err:
        raise http_errors.BadRequest(str(err)) from err


@router.get('/{jid}', operation_id='job_retrieve')
async def job_retrieve(jid: IntJid, job_service: JobServiceDependency) -> Job:
    _jid = JID(jid)

    try:
        job: Job = await job_service.get_job(_jid)
        return job
    except ValidationError as e:
        raise http_errors.InternalServerError(detail=e.errors()) from e
    except JobDoesNotExistsException as e:
        raise http_errors.NotFound(detail=str(e)) from e


@router.post('', operation_id='job_create')
async def job_create(item: CreateJobRequest, job_service: JobServiceDependency) -> CreateJobResponse:
    try:
        jid: JID = await job_service.create_job(
            JobCreate.model_validate(
                {
                    **item.model_dump(),
                }
            )
        )

        return CreateJobResponse.model_validate({'jid': str(jid)})
    except JobCreateException as error:
        raise http_errors.BadGateway(detail=str(error)) from error


@router.get('/{jid}/returns-count', operation_id='job_returns_count')
async def job_returns_count(jid: IntJid, job_service: JobServiceDependency) -> Annotated[int, Field(gte=0)]:
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
        return Job(**{'status': Job.JobStatus.started, **data}).model_dump_json(by_alias=True)

    secure_websocket = PubSubAuthenticatedWebSocket(websocket, rdb)
    await secure_websocket.handle_pubsub({'job:*:new': job_new_handler})


@ws_router.websocket('/{jid}/return')
async def jobs_endpoint_websocket(
    jid: IntJid,
    websocket: WebSocket,
    rdb: RedisDependency,
) -> None:
    ts = JID(jid).to_timestamp()
    jid_in_jobs = bool(await rdb.zcount('jobs', min=ts, max=ts))
    if not jid_in_jobs:
        msg = f'Job not found by JID={jid}'
        raise http_errors.WebSocketPolicyViolation(msg)

    secure_websocket = PubSubAuthenticatedWebSocket(websocket, rdb)
    await secure_websocket.handle_pubsub({f'job:{jid}:return': JobResult})
