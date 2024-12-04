import json
import os
import websockets

from base64 import b64encode
from httpx import Client, Response
from utilities.logger_utils import logger


class ApiClient(Client):

    def __init__(self):
        super().__init__(base_url=f'{os.getenv("RESOURCE_URL")}')
        self.ws = WsClient(base_url=f'{os.getenv("RESOURCE_URL").replace("http" or "https", "ws")}')

    def request(self, method, url, **kwargs) -> Response:
        username = os.getenv("BASIC_AUTH_LOGIN")
        password = os.getenv("BASIC_AUTH_PASSWORD")
        if eval(os.getenv('USE_BASIC_AUTH')):
            auth_header = f"Basic {b64encode(f'{username}:{password}'.encode()).decode()}"
            self.headers.update({"Authorization": auth_header})
        if eval(os.getenv('USE_LOGS')):
            logger.info(f'{method} {url}')

        return super().request(method, url, **kwargs)


class WsClient:
    def __init__(self, base_url):
        self.base_url = base_url
        self.websocket = None

    async def connect(self, endpoint):
        url = f'{self.base_url.replace("http" or "https", "ws")}{endpoint}'
        self.websocket = await websockets.connect(url)

    async def send(self, message):
        await self.websocket.send(json.dumps(message))

    async def receive(self):
        message = await self.websocket.recv()
        return json.loads(message)

    async def listen(self):
        async for message in self.websocket:
            data = json.loads(message)
            yield data

    async def close(self):
        await self.websocket.close()
