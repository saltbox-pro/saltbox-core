from __future__ import annotations

import asyncio
import datetime
import json
import logging

from contextlib import asynccontextmanager
from typing import Annotated

import pydantic
from redis.asyncio.client import PubSub

from fastapi import FastAPI, Form, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi_offline import FastAPIOffline
from pydantic import ValidationError

from app import http_errors
from app.config import APP_NAME, SETTINGS, LOG_CONFIG
from app.redis import POOL, RedisDependency
from app.models.salt import (
    CreateJobRequest, CreateJobResponse, Job, JobResult
)
from app.salt_http_client import SaltHttpClient, SaltHttpClientError
from app.utilities.jid import jid_from_datetime

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
        end_datetime: datetime.datetime = None
) -> list[Job]:
    if end_datetime is None:
        end_datetime = datetime.datetime.now() + datetime.timedelta(hours=1)

    start = jid_from_datetime(start_datetime)
    end = jid_from_datetime(end_datetime)

    res_ = await rdb.zrange('jobs', start=end, end=start, desc=True, byscore=True)
    res = [json.loads(i) for i in res_]

    try:
        return [Job(**i) for i in res]
    except ValidationError as err:
        raise http_errors.InternalServerError(detail=err.errors())


@APP.get('/jobs/{tag}')
async def get_job_endpoint(tag: str, rdb: RedisDependency) -> Job:
    res_ = await rdb.zrange('jobs', start=int(tag), end=int(tag), byscore=True)

    if not res_:
        raise http_errors.NotFound(detail='Job not found')

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
    # TODO Check jid tz
    return CreateJobResponse.model_validate(ret)


@APP.get('/jobs/{jid}/rets')
async def get_job_rets_endpoint(jid: str, rdb: RedisDependency) -> list[JobResult]:
    res_ = await rdb.hgetall(name=f'job.rets:{jid}')

    res = []
    for _, ret in res_.items():
        data = json.loads(ret)

        try:
            res.append(JobResult(**data))
        except ValidationError as e:
            raise http_errors.InternalServerError(detail=e.errors())

    return res


@APP.websocket('/ws_jobs')
async def websocket_jobs_rets_endpoint(websocket: WebSocket, rdb: RedisDependency):
    await websocket.accept()

    async def reader(pubsub: PubSub) -> None:
        async for message in pubsub.listen():
            if message['type'] not in PubSub.PUBLISH_MESSAGE_TYPES:
                LOGGER.debug('Skipping service message: %s', message)
                continue
            decoded_data = message['data'].decode()
            data = json.loads(decoded_data)
            job = Job(**data)
            await websocket.send_text(job.model_dump_json(by_alias=True))

    try:
        async with rdb.pubsub() as pubsub:
            await pubsub.psubscribe('job:*')
            await asyncio.create_task(reader(pubsub))

    except WebSocketDisconnect:
        client = websocket.client
        if not client:
            LOGGER.info('/ws_jobs websocket has been disconnected')
        else:
            LOGGER.info(
                '/ws_jobs websocket for %s:%i has been disconnected',
                client.host,
                client.port)


@APP.websocket('/ws_jobs/{jid}/rets')
async def websocket_jobs_endpoint(websocket: WebSocket, jid: str, rdb: RedisDependency):
    # TODO Use https://github.com/encode/broadcaster if need broadcasts
    await websocket.accept()

    async def reader(pubsub: PubSub):
        async for message in pubsub.listen():
            if message['type'] not in PubSub.PUBLISH_MESSAGE_TYPES:
                LOGGER.debug('Skipping service message: %s', message)
                continue
            decoded_data = message['data'].decode()
            data = json.loads(decoded_data)
            result = JobResult(**data).model_dump_json(by_alias=True)
            await websocket.send_text(result)

    try:
        async with rdb.pubsub() as pubsub:
            await pubsub.psubscribe(f'job.rets:{jid}')
            await asyncio.create_task(reader(pubsub))

    except WebSocketDisconnect:
        client = websocket.client
        if not client:
            LOGGER.info('/ws_jobs websocket has been disconnected')
        else:
            LOGGER.info(
                '/ws_jobs websocket for %s:%i has been disconnected',
                client.host,
                client.port)
