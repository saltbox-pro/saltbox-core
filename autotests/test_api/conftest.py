import allure  # type: ignore
import pytest
import redis
import requests
import os
import websockets  # type: ignore
import json

from utils import delete_job_from_zset_on_redis

REDIS_CLIENT = redis.Redis(host='localhost', port=6379, db=0)


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
                allure.attach(
                    json.dumps(data, indent=2),
                    name='WebSocket Message',
                    attachment_type=allure.attachment_type.JSON,
                )
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


@pytest.fixture(scope='session')
def api():
    base_url = os.environ.get('FASTMS_CORE_URL', 'http://localhost/api/core')
    return APIClient(base_url=base_url)


@pytest.fixture(scope='session')
def create_jid(api):
    payload = {
        'tgt': '*',
        'tgt_type': 'glob',
        'fun': 'test.ping',
        'arg': [],
        'kwarg': {},
    }
    response = api.post('/jobs', json=payload)
    assert response.status_code == 200, f'Error, the server has returned code {response.status_code}, no created jid for test'
    response_json = response.json()
    jid = response_json['return'][0]['jid']
    yield jid

    # Delete created jobs
    REDIS_CLIENT.delete(f'job:{jid}:return')
    delete_job_from_zset_on_redis(jid)


@pytest.fixture(scope='session')
def create_data(api):
    payload = {
        'tgt': '*',
        'tgt_type': 'glob',
        'fun': 'grains.items',
        'kwarg': {},
    }
    response = api.post('/jobs', json=payload)
    assert response.status_code == 200, f'Error, the server has returned code {response.status_code}, no created data for test'
    response_json = response.json()
    if not response_json:
        pytest.fail('Failed to create grains.items job or the answer came empty')
    mid_list = response_json['return'][0]['minions']
    if mid_list:
        yield mid_list
    else:
        pytest.fail('No available minions found.')

    # Delete created data
    for i in mid_list:
        REDIS_CLIENT.delete(f'minion:{i}:grains')
    jid = response_json['return'][0]['jid']
    REDIS_CLIENT.delete(f'job:{jid}:return')
    delete_job_from_zset_on_redis(jid)
