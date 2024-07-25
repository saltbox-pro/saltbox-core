import allure
import pytest
import requests
import os
import websockets
import json


class WebSocketClient:
    def __init__(self, base_url):
        self.base_url = base_url

    async def connect(self, endpoint):
        url = f'{self.base_url.replace("http" or "https", "ws")}{endpoint}'
        with allure.step(f'Connection to {url}'):
            self.websocket = await websockets.connect(url)

    async def send(self, message):
        with allure.step('Sending message'):
            allure.attach(json.dumps(message))
            await self.websocket.send(json.dumps(message))

    async def receive(self):
        with allure.step('Receive message'):
            message = await self.websocket.recv()
            return json.loads(message)

    async def listen(self):
        with allure.step('Listening message'):
            async for message in self.websocket:
                data = json.loads(message)
                allure.attach(json.dumps(data, indent=2),
                              name="WebSocket Message",
                              attachment_type=allure.attachment_type.JSON)
                yield data

    async def close(self):
        with allure.step('Close connection'):
            await self.websocket.close()


class APIClient:
    def __init__(self, base_url):
        self.base_url = base_url
        self.websocket_client = WebSocketClient(base_url)

    def get(self, endpoint, params=None, headers=None):
        url = f'{self.base_url}{endpoint}'
        with allure.step(f'Sending GET request to url: {url}'):
            return requests.get(url=url, params=params, headers=headers)

    def post(self, endpoint, params=None, headers=None, json=None, data=None):
        url = f'{self.base_url}{endpoint}'
        with allure.step(f'Sending POST request to url: {url}'):
            return requests.post(url=url, params=params, headers=headers, json=json, data=data)


@pytest.fixture(scope='module')
def api():
    base_url = os.environ.get('FASTMS_CORE_URL', 'http://localhost:8000')
    return APIClient(base_url=base_url)


@pytest.fixture(scope='module')
def create_jid(api):
    payload = {
        'tgt': '*',
        'tgt_type': 'glob',
        'fun': 'test.ping',
        'arg': [],
        'kwarg': {}
    }
    response_json = api.post('/jobs', json=payload).json()
    jid = response_json['return'][0]['jid']
    return jid
