import asyncio
import time
import json
import pytest
import redis
import allure  # type: ignore
import websockets  # type: ignore
from utils import create_sleep_job, create_new_job

REDIS_CLIENT = redis.Redis(host='localhost', port=6379, db=0)


@pytest.mark.asyncio
@allure.feature('A websocket endpoints')
@allure.title('Connecting to ws endpoind and checking changing jobs')
async def test_websocket_jobs(api):
    await api.websocket_client.connect('/jobs')

    with allure.step('Creating a new job to ensure that the client receives the required information'):
        jid = create_new_job(api)
    try:
        message = await asyncio.wait_for(api.websocket_client.listen().__anext__(), timeout=3)
        assert message['jid'] == jid
    except asyncio.TimeoutError:
        pytest.fail('Timeout: No message received from the server within the expected time.')

    await api.websocket_client.close()
    await asyncio.sleep(0.1)
    REDIS_CLIENT.delete(f'job:{jid}:return')


@pytest.mark.asyncio
@allure.feature('A websocket endpoints')
@allure.title(
    'A websocket connection has been established for the job and the message has been received /ws_jobs/{jid}/return'
)
async def test_websocket_jobs_return(api):
    with allure.step('Creating a new job and get jid'):
        jid = create_sleep_job(api)
    await api.websocket_client.connect(f'/jobs/{jid}/return')

    with allure.step('Checking that client receives the required information'):
        try:
            message = await asyncio.wait_for(api.websocket_client.listen().__anext__(), timeout=3)
            assert message['jid'] == jid
        except asyncio.TimeoutError:
            pytest.fail('Timeout: No message received from the server within the expected time.')
        finally:
            await api.websocket_client.close()
            REDIS_CLIENT.delete(f'job:{jid}:return')


@pytest.mark.asyncio
@allure.feature('A websocket endpoints')
@allure.title('Checking that the connection is unavailable for no valid type (str) jobs /ws_jobs/{jid}/return')
async def test_websocket_no_valid_jobs_return(api):
    with allure.step('Checking that the server returns an error'):
        with pytest.raises(websockets.exceptions.InvalidHandshake):
            await api.websocket_client.connect('/ws_jobs/asdasd/return')
    await api.websocket_client.close()


@pytest.mark.asyncio
@allure.feature('A websocket endpoints')
@allure.title('Checking that the connection has been established from the minion')
async def test_websocket_connection_to_minion(api, create_data):
    mid = create_data[0]

    with allure.step('We establish a connection with a specific minion'):
        await api.websocket_client.connect(f'/minion/{mid}/grains')
    await api.websocket_client.close()


@pytest.mark.asyncio
@allure.feature('A websocket endpoints')
@allure.title('Checking that the published message has been received from the server')
async def test_websocket_received_pub_message(api, create_data):
    mid = create_data[0]

    with allure.step('We establish a connection with a specific minion'):
        await api.websocket_client.connect(f'/minion/{mid}/grains')
    await asyncio.sleep(0.1)

    with allure.step('We are publishing a message on the Redis'):
        pub_message = '{"os": "Linux"}'
        REDIS_CLIENT.publish(f'minion:{mid}:grains', pub_message)

    with allure.step(
        f'We verify that the published message {pub_message} has been successfully received from the server.'
    ):
        try:
            message = await asyncio.wait_for(api.websocket_client.listen().__anext__(), timeout=3)
            assert json.loads(pub_message) == message
        except asyncio.TimeoutError:
            pytest.fail('Timeout: No message received from the server within the expected time.')
        finally:
            await api.websocket_client.close()
