# uvicorn main:app --host 192.168.122.197 --port 80 --reload
import asyncio
import datetime
import json
from typing import Union, List, Dict, Any

import redis.asyncio as redis
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request
from pydantic import BaseModel
from pydantic import ValidationError
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.encoders import jsonable_encoder
# from salt.client import LocalClient

from app.deps import RedisDep


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
    async def send_personal_json_message(message: Union[List, Dict], websocket: WebSocket):
        await websocket.send_json(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)


app = FastAPI(
    title='FastMS'
)


manager = ConnectionManager()


class Job(BaseModel):
    # example:
    # {
    #     "jid": "20240422071217916112",
    #     "tgt_type": "glob",
    #     "tgt": "*",
    #     "user": "root",
    #     "fun": "test.ping",
    #     "arg": [],
    #     "minions": ["master.master"],
    #     "missing": [],
    #     "_stamp": "2024-04-22T07:12:17.932302"
    # }
    jid: str
    tgt: str
    tgt_type: str
    user: str
    fun: str
    arg: Union[None, List] = None
    kwarg: Union[None, Dict] = None
    minions: List[str]
    _stamp: str


class JobPost(BaseModel):
    tgt: str = '*'
    tgt_type: str = "glob"
    fun: str = 'test.ping'
    arg: Union[None, List] = None
    kwarg: Union[None, Dict] = None


class JobResult(BaseModel):
    # example:
    # {
    #     "cmd": "_return",
    #     "id": "master.master",
    #     "success": True,
    #     "return": True,
    #     "retcode": 0,
    #     "jid": "20240422081827358198",
    #     "fun": "test.ping",
    #     "fun_args": [],
    #     "user": "root",
    #     "_stamp": "2024-04-22T08:18:27.509512"
    # }
    _cmd: str
    id: str
    success: bool
    retdata: Any
    retcode: int
    jid: str
    fun: str
    fun_args: Union[None, List] = None
    fun_kwarg: Union[None, Dict] = None
    user: str
    _stamp: str


@app.post('/cherrypy_fake_rest_auth', status_code=200)
async def run_fake_auth(request: Request):
    await request.body()
    data = ['.*', '@wheel', '@jobs', '@runner']
    json_compatible_item_data = jsonable_encoder(data)
    return JSONResponse(content=json_compatible_item_data)


@app.get('/jobs')
async def get_jobs_endpoint(
        start_datetime: datetime.datetime,
        end_datetime: datetime.datetime, rdb: RedisDep
) -> List[Job]:
    start = get_jid(datatime_val=start_datetime)
    end = get_jid(datatime_val=end_datetime)

    # res_count = await r.zcount(name='jobs', min=start, max=end)
    res_ = await rdb.zrange('jobs', start=end, end=start, desc=True, byscore=True)
    res = [json.loads(i) for i in res_]

    try:
        return [Job(**i) for i in res]
    except ValidationError as err:
        raise HTTPException(status_code=404, detail=err.errors())


@app.get('/jobs/{tag}')
async def get_job_endpoint(tag: str, rdb: RedisDep) -> Job:
    res_ = await rdb.zrange('jobs', start=int(tag), end=int(tag), byscore=True)

    if not res_:
        raise HTTPException(status_code=404, detail='Job not found')

    res = json.loads(res_[0])

    try:
        return Job(**res)
    except ValidationError as e:
        raise HTTPException(status_code=404, detail=e.errors())


# @app.post('/jobs')
# async def create_job_endpoint(item: JobPost) -> str:
#     local_client = LocalClient()
#     jid = local_client.cmd_async(
#         tgt=item.tgt,
#         tgt_type=item.tgt_type,
#         fun=item.fun,
#         arg=item.arg,
#         kwarg=item.kwarg
#     )
#     return jid


@app.get('/jobs/{jid}/rets')
async def get_job_rets_endpoint(jid: str, rdb: RedisDep) -> List[JobResult]:
    res_ = await rdb.hgetall(name=f'job.rets:{jid}')

    res = []
    for _, ret in res_.items():
        data = json.loads(ret)
        data['retdata'] = data.pop('return')

        try:
            res.append(JobResult(**data))
        except ValidationError as e:
            raise HTTPException(status_code=404, detail=e.errors())

    return res


@app.websocket('/ws_jobs')
async def websocket_jobs_rets_endpoint(websocket: WebSocket, rdb: RedisDep):
    await manager.connect(websocket)

    async def reader(channel: redis.client.PubSub):
        while True:
            message = await channel.get_message(ignore_subscribe_messages=True)
            if message is not None:
                # tag = message['channel'].decode("utf-8")
                decoded_data = message['data'].decode("utf-8")
                data = json.loads(decoded_data)

                try:
                    data = Job(**data)
                    await manager.send_personal_json_message(data.model_dump(), websocket)
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
        manager.disconnect(websocket)


@app.websocket('/ws_jobs/{jid}/rets')
async def websocket_jobs_endpoint(websocket: WebSocket, jid: str, rdb: RedisDep):
    await manager.connect(websocket)

    async def reader(channel: redis.client.PubSub):
        while True:
            message = await channel.get_message(ignore_subscribe_messages=True)
            if message is not None:
                decoded_data = message['data'].decode("utf-8")
                data = json.loads(decoded_data)
                data['retdata'] = data.pop('return')

                try:
                    data = JobResult(**data)
                    await manager.send_personal_json_message(data.model_dump(), websocket)
                except ValidationError:
                    ...

    try:
        async with rdb.pubsub() as pubsub:
            await pubsub.psubscribe(f'job.rets:{jid}')
            future = asyncio.create_task(reader(pubsub))
            await future

    except WebSocketDisconnect:
        manager.disconnect(websocket)

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
async def get():
    # TODO
    return HTMLResponse(html)


# @app.get('/jobs/stat')
# async def get_jobs():
#     res_count = await r.zcard(name='jobs')
#     first = await r.zrange('jobs', start=0, end=0)
#     last = await r.zrange('jobs', start=-1, end=-1)
#     return res_count, json.loads(first[0]), json.loads(last[0])
