import datetime
import json
import logging.config
from typing import Annotated

import pydantic
import redis.exceptions as redis_exceptions
from fastapi import APIRouter, WebSocket
from pydantic import Field, ValidationError

from fastms_core import http_errors
from fastms_core.config import LOG_CONFIG, SETTINGS
from fastms_core.db.redis import RedisDependency
from fastms_core.jobs.schemas import CreateJobRequest, CreateJobResponse, GetJobReturnResponse, IntJid, Job, JobResult
from fastms_core.utilities.jid import JID, JidError
from fastms_core.utilities.salt import SaltJobCreateError, create_job
from fastms_core.utilities.websocket import PubSubAuthenticatedWebSocket

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
    rdb: RedisDependency, start_datetime: pydantic.PastDatetime, end_datetime: datetime.datetime | None = None
) -> list[Job]:
    if end_datetime is None:
        end_datetime = datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=1)

    try:
        start = JID.from_datetime(start_datetime).to_timestamp()
        end = JID.from_datetime(end_datetime).to_timestamp()
    except JidError as err:
        msg = f'Invalid range: {err}'
        raise http_errors.BadRequest(msg) from err

    res_ = await rdb.zrange('jobs', start=end, end=start, desc=True, byscore=True)  # type: ignore[call-overload]
    res = [json.loads(i) for i in res_]

    try:
        return [Job(**i) for i in res]
    except ValidationError as err:
        raise http_errors.InternalServerError(detail=err.errors()) from err


@router.get('/{jid}', operation_id='job_retrieve')
async def job_retrieve(jid: IntJid, rdb: RedisDependency) -> Job:
    ts = JID(jid).to_timestamp()
    logger.debug('ts=%s', ts)

    res_ = await rdb.zrange('jobs', start=ts, end=ts, byscore=True)  # type: ignore[call-overload]

    if not res_:
        raise http_errors.NotFound(detail='Job not found')
    elif len(res_) > 1:
        raise http_errors.InternalServerError(detail=f'Multiple jobs for JID {jid}')

    res = json.loads(res_[0])

    try:
        return Job(**res)
    except ValidationError as e:
        raise http_errors.InternalServerError(detail=e.errors()) from e


@router.post('', operation_id='job_create')
async def job_create(item: CreateJobRequest, rdb: RedisDependency) -> CreateJobResponse:
    try:
        jid: str = await create_job(
            tgt=item.tgt,
            tgt_type=item.tgt_type,
            fun=item.fun,
            arg=item.arg,
            kwarg=item.kwarg,
            salt_master='salt-master',  # TODO: get salt master from request
            rdb=rdb,
        )

        return CreateJobResponse.model_validate({"jid": jid})
    except SaltJobCreateError as error:
        raise http_errors.BadGateway(detail=str(error)) from error


@router.get('/{jid}/returns-count', operation_id='job_returns_count')
async def job_returns_count(jid: IntJid, rdb: RedisDependency) -> Annotated[int, Field(gte=0)]:
    """
    How many return data records for job at the moment.

    To be used in pair with GET /jobs/{jid}/return cycle.
    """
    length = await rdb.hlen(name=f'job:{jid}:return')
    if not length:
        return 0
    return length


@router.get('/{jid}/return', operation_id='job_returns_list')
async def job_returns_list(
    jid: IntJid,
    rdb: RedisDependency,
    count: Annotated[int, Field(gt=0, lt=SETTINGS.max_count)] = 10,
    cursor: pydantic.NonNegativeInt = 0,
) -> GetJobReturnResponse:
    """
    Get list of returned by minions data.

    Amount is not guaranteed to be exactly count.
    """
    try:
        next_cur, records = await rdb.hscan(name=f'job:{jid}:return', cursor=cursor, count=count)
    except redis_exceptions.ResponseError as exc:
        raise http_errors.BadGateway(detail=str(exc)) from exc

    res = []
    for _, ret in records.items():
        data = json.loads(ret)

        try:
            res.append(JobResult(**data))
        except ValidationError as e:
            raise http_errors.InternalServerError(detail=e.errors()) from e

    return GetJobReturnResponse(cursor=next_cur, result=res, length=len(res))


# TODO Use https://github.com/encode/broadcaster if need broadcasts
@ws_router.websocket('')
async def jobs_rets_websocket(websocket: WebSocket, rdb: RedisDependency) -> None:
    secure_websocket = PubSubAuthenticatedWebSocket(websocket, rdb)
    await secure_websocket.handle_pubsub(channel='job:*:new', schema=Job)


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
    await secure_websocket.handle_pubsub(channel=f'job:{jid}:return', schema=JobResult)
