import asyncio
import datetime
import json
import logging

from typing import Annotated, Union

import redis.asyncio as redis

from fastapi import Form, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi_offline import FastAPIOffline
from pydantic import ValidationError

from app import http_errors
from app.config import SETTINGS
from app.deps import RedisDep
from app.models.salt import Job, JobPost, JobResult
from app.salt_http_client import SaltHttpClient, SaltHttpClientError

FormStr = Annotated[str, Form()]

SALT_CLIENT = SaltHttpClient(
    SETTINGS.salt_url,
    strict_ssl=False,
    username=SETTINGS.salt_username,
    password=SETTINGS.salt_password)
LOGGER = logging.getLogger(__name__)


def get_jid(datatime_val: datetime.datetime) -> int:
    return int("{:%Y%m%d%H%M%S%f}".format(datatime_val))


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    @staticmethod
    async def send_personal_message(message: str, websocket: WebSocket):
        await websocket.send_text(message)

    @staticmethod
    async def send_personal_json_message(message: Union[list, dict], websocket: WebSocket):
        await websocket.send_json(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)


app = FastAPIOffline(title='FastMS')
MANAGER = ConnectionManager()


@app.post('/salt_auth')
async def salt_auth_endpoint(username: FormStr, password: FormStr) -> JSONResponse:
    """ For salt.auth.rest """
    if username == SETTINGS.salt_username and password == SETTINGS.salt_password:
        acl = ['.*', '@wheel', '@jobs', '@runner']
        return JSONResponse(content=jsonable_encoder(acl))
    else:
        raise http_errors.Unauthorized(f'Unknown user {username} or invalid password')


@app.get('/jobs')
async def get_jobs_endpoint(
        start_datetime: datetime.datetime,
        end_datetime: datetime.datetime, rdb: RedisDep
) -> list[Job]:
    start = get_jid(datatime_val=start_datetime)
    end = get_jid(datatime_val=end_datetime)

    # res_count = await r.zcount(name='jobs', min=start, max=end)
    res_ = await rdb.zrange('jobs', start=end, end=start, desc=True, byscore=True)
    res = [json.loads(i) for i in res_]

    try:
        return [Job(**i) for i in res]
    except ValidationError as err:
        raise http_errors.InternalServerError(detail=err.errors())


@app.get('/jobs/{tag}')
async def get_job_endpoint(tag: str, rdb: RedisDep) -> Job:
    res_ = await rdb.zrange('jobs', start=int(tag), end=int(tag), byscore=True)

    if not res_:
        raise http_errors.NotFound(detail='Job not found')

    res = json.loads(res_[0])

    try:
        return Job(**res)
    except ValidationError as e:
        raise http_errors.InternalServerError(detail=e.errors())


# TODO Close salt_master:8001
# TODO make one-command container for salt-api
@app.post('/jobs')
async def create_job_endpoint(item: JobPost) -> object:
    # TODO Typification of return
    await SALT_CLIENT._login()  # FIXME make auto
    try:
        resp = await SALT_CLIENT.run_job(
            tgt=item.tgt,
            fun=item.fun,
            arg=item.arg,
            kwarg=item.kwarg,
            tgt_type=item.tgt_type)
    except SaltHttpClientError as error:
        raise http_errors.BadGateway(detail=str(error))
    jid = resp
    return jid


@app.get('/jobs/{jid}/rets')
async def get_job_rets_endpoint(jid: str, rdb: RedisDep) -> list[JobResult]:
    res_ = await rdb.hgetall(name=f'job.rets:{jid}')

    res = []
    for _, ret in res_.items():
        data = json.loads(ret)
        data['retdata'] = data.pop('return')

        try:
            res.append(JobResult(**data))
        except ValidationError as e:
            raise http_errors.InternalServerError(detail=e.errors())

    return res


@app.websocket('/ws_jobs')
async def websocket_jobs_rets_endpoint(websocket: WebSocket, rdb: RedisDep):
    await MANAGER.connect(websocket)

    async def reader(channel: redis.client.PubSub):
        while True:
            message = await channel.get_message(ignore_subscribe_messages=True)
            if message is not None:
                # tag = message['channel'].decode("utf-8")
                decoded_data = message['data'].decode("utf-8")
                data = json.loads(decoded_data)

                try:
                    data = Job(**data)
                    await MANAGER.send_personal_json_message(data.model_dump(), websocket)
                except ValidationError:
                    ...

    try:
        async with rdb.pubsub() as pubsub:
            await pubsub.psubscribe('job:*')
            # await pubsub.psubscribe('job:*', 'job.rets:*')
            future = asyncio.create_task(reader(pubsub))
            # await r.publish("job:1", "Hello")
            await future

    except WebSocketDisconnect:
        MANAGER.disconnect(websocket)


@app.websocket('/ws_jobs/{jid}/rets')
async def websocket_jobs_endpoint(websocket: WebSocket, jid: str, rdb: RedisDep):
    await MANAGER.connect(websocket)

    async def reader(channel: redis.client.PubSub):
        while True:
            message = await channel.get_message(ignore_subscribe_messages=True)
            if message is not None:
                decoded_data = message['data'].decode("utf-8")
                data = json.loads(decoded_data)
                data['retdata'] = data.pop('return')

                try:
                    data = JobResult(**data)
                    await MANAGER.send_personal_json_message(data.model_dump(), websocket)
                except ValidationError:
                    ...

    try:
        async with rdb.pubsub() as pubsub:
            await pubsub.psubscribe(f'job.rets:{jid}')
            future = asyncio.create_task(reader(pubsub))
            await future

    except WebSocketDisconnect:
        MANAGER.disconnect(websocket)

html = """
<!DOCTYPE html>
<html>
    <head>
        <title>charon</title>
    </head>
    <body>
        <h1>salt charon</h1>
        <form action="" onsubmit="sendMessage(event)">
            <input type="text" id="messageText" autocomplete="off"/>
            <button>Send</button>
        </form>
        <ul id='messages'>
        </ul>
        <script>
            var ws = new WebSocket("ws://192.168.122.197:80/ws_jobs");
            ws.onmessage = function(event) {
                var messages = document.getElementById('messages')
                var message = document.createElement('li')
                var content = document.createTextNode(event.data)
                message.appendChild(content)
                messages.appendChild(message)
            };
            function sendMessage(event) {
                var input = document.getElementById("messageText")
                ws.send(input.value)
                input.value = ''
                event.preventDefault()
            }
        </script>
    </body>
</html>
"""


@app.get('/')
async def get() -> HTMLResponse:
    # TODO
    return HTMLResponse(html)


@app.get('/jobs/stat')
async def get_jobs_stat():
    #res_count = await r.zcard(name='jobs')
    #first = await r.zrange('jobs', start=0, end=0)
    #last = await r.zrange('jobs', start=-1, end=-1)
    #return res_count, json.loads(first[0]), json.loads(last[0])
    raise http_errors.NotImplemented('KAMINSUN')
