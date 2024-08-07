from __future__ import annotations

import asyncio
import datetime
import json
import logging

from contextlib import asynccontextmanager
from typing import Annotated, Any

import pydantic

from fastapi import FastAPI, Form, WebSocket
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi_offline import FastAPIOffline
from pydantic import ValidationError
from redis.asyncio.client import PubSub

from fastms_core import http_errors
from fastms_core.config import APP_NAME, SETTINGS, LOG_CONFIG
from fastms_core.redis import POOL, RedisDependency
from fastms_core.models.salt import (
    CreateJobRequest, CreateJobResponse, IntJid, Job, JobResult
)
from fastms_core.salt_http_client import SaltHttpClient, SaltHttpClientError
from fastms_core.utilities.jid import JID, JidError
from fastms_core.websocket import IsSocketDisconnected

FormStr = Annotated[str, Form()]

SALT_CLIENT = SaltHttpClient(
    SETTINGS.salt_url,
    strict_ssl=False,
    username=SETTINGS.salt_username,
    password=SETTINGS.salt_password)
LOGGER = logging.getLogger(__name__)

logging.config.dictConfig(LOG_CONFIG.dict())


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await POOL.aclose()


APP = FastAPIOffline(title=APP_NAME, lifespan=lifespan)

APP.add_middleware(
    CORSMiddleware,
    allow_origins=SETTINGS.origins,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


@APP.post('/salt_auth')
async def salt_auth_endpoint(username: FormStr, password: FormStr) -> JSONResponse:
    """ For salt.auth.rest """
    if username == SETTINGS.salt_username and password == SETTINGS.salt_password:
        acl = ['.*', '@wheel', '@jobs', '@runner']
        return JSONResponse(content=jsonable_encoder(acl))
    else:
        raise http_errors.Unauthorized(f'Unknown user {username} or invalid password')


@APP.get('/jobs')
async def get_jobs_endpoint(
        rdb: RedisDependency,
        start_datetime: pydantic.PastDatetime,
        end_datetime: datetime.datetime | None = None
) -> list[Job]:
    if end_datetime is None:
        end_datetime = datetime.datetime.now() + datetime.timedelta(hours=1)

    try:
        start = JID.from_datetime(start_datetime).to_timestamp()
        end = JID.from_datetime(end_datetime).to_timestamp()
    except JidError as err:
        raise http_errors.BadRequest(f'Invalid range: {err}')

    res_ = await rdb.zrange('jobs', start=end, end=start, desc=True, byscore=True)
    res = [json.loads(i) for i in res_]

    try:
        return [Job(**i) for i in res]
    except ValidationError as err:
        raise http_errors.InternalServerError(detail=err.errors())


@APP.get('/jobs/{jid}')
async def get_job_endpoint(jid: IntJid, rdb: RedisDependency) -> Job:
    ts = JID(jid).to_timestamp()

    res_ = await rdb.zrange('jobs', start=ts, end=ts, byscore=True)

    if not res_:
        raise http_errors.NotFound(detail='Job not found')
    elif len(res_) > 1:
        raise http_errors.InternalServerError(detail=f'Multiple jobs for JID {jid}')

    res = json.loads(res_[0])

    try:
        return Job(**res)
    except ValidationError as e:
        raise http_errors.InternalServerError(detail=e.errors())


@APP.post('/jobs')
async def create_job_endpoint(item: CreateJobRequest) -> CreateJobResponse:
    try:
        ret = await SALT_CLIENT.run_job(
            tgt=item.tgt,
            fun=item.fun,
            arg=item.arg,
            kwarg=item.kwarg,
            tgt_type=item.tgt_type)
    except SaltHttpClientError as error:
        raise http_errors.BadGateway(detail=str(error))
    return CreateJobResponse.model_validate(ret)


@APP.get('/jobs/{jid}/return')
async def get_job_rets_endpoint(jid: IntJid, rdb: RedisDependency) -> list[JobResult]:
    res_ = await rdb.hgetall(name=f'job:{jid}:return')

    res = []
    for _, ret in res_.items():
        data = json.loads(ret)

        try:
            res.append(JobResult(**data))
        except ValidationError as e:
            raise http_errors.InternalServerError(detail=e.errors())

    return res


# TODO Use https://github.com/encode/broadcaster if need broadcasts
@APP.websocket('/jobs')
async def jobs_rets_websocket(
    websocket: WebSocket,
    rdb: RedisDependency
) -> None:
    await websocket.accept()

    async def reader(pubsub: PubSub) -> None:
        async for message in pubsub.listen():
            if message['type'] not in PubSub.PUBLISH_MESSAGE_TYPES:
                LOGGER.debug('Skipping service message: %s', message)
                continue
            data_str = message['data'].decode()
            data = json.loads(data_str)
            # FIXME LOGGER.error(f'>>> {data}')
            job = Job(**data)
            with IsSocketDisconnected(websocket) as disconnect:
                await websocket.send_text(job.model_dump_json(by_alias=True))
            if disconnect:
                return

    async with rdb.pubsub() as pubsub:
        await pubsub.psubscribe('job:*')
        await asyncio.create_task(reader(pubsub))


@APP.websocket('/jobs/{jid}/return')
async def jobs_endpoint_websocket(
    jid: IntJid,
    websocket: WebSocket,
    rdb: RedisDependency,
) -> None:
    ts = JID(jid).to_timestamp()
    jid_in_jobs = bool(await rdb.zcount('jobs', min=ts, max=ts))
    if not jid_in_jobs:
        raise http_errors.WebSocketPolicyViolation(f'Job not found by JID={jid}')

    await websocket.accept()

    async def reader(pubsub: PubSub):
        async for message in pubsub.listen():
            if message['type'] not in PubSub.PUBLISH_MESSAGE_TYPES:
                LOGGER.debug('Skipping service message: %s', message)
                continue
            data = json.loads(message['data'].decode())
            result = JobResult(**data).model_dump_json(by_alias=True)
            with IsSocketDisconnected(websocket) as disconnect:
                await websocket.send_text(result)
            if disconnect:
                return

    async with rdb.pubsub() as pubsub:
        await pubsub.psubscribe(f'job:{jid}:return')
        await asyncio.create_task(reader(pubsub))

# TODO List minions (with grains)


@APP.get('/minion/{mid}/grains')
async def get_minion_grains_endpoint(mid: str, rdb: RedisDependency) -> dict[str, Any]:
    data = await rdb.hgetall(name=f'minion:{mid}:grains')
    if not data:
        raise http_errors.NotFound(f'No grains kept for {mid}')
    return {k: json.loads(val) for k, val in data.items()}


@APP.get('/minion/{mid}/grain/{grain}')
async def get_minion_the_grain_endpoint(mid: str, grain: str, rdb: RedisDependency) -> Any:
    """
    Get specific minion grain

    There are 404 for null value
    """
    value = await rdb.hget(name=f'minion:{mid}:grains', key=grain)
    if value is None:
        raise http_errors.NotFound(f'No grain {grain} value for {mid}')
    return json.loads(value)
