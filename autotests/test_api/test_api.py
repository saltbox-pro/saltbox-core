import time

import pytest
import json
import redis
from datetime import datetime, timedelta
import allure  # type: ignore
from utils import attach_json_to_allure, check_error_message, delete_job_from_zset_on_redis


REDIS_CLIENT = redis.Redis(host='localhost', port=6379, db=0)


@allure.feature('Endpoint GET /jobs/{jid}')
@allure.title('Sending a valid request to receive a specific job')
def test_get_specific_job(api, create_jid):
    with allure.step('Creating new job and get jid'):
        pass
    response = api.get(f'/jobs/{create_jid}')

    with allure.step('Checking that the server has returned the status code == 200'):
        error_msg = f'Error, the server has returned code {response.status_code}'
        assert response.status_code == 200, error_msg
    response_json = response.json()

    with allure.step('Checking that the response contains all keys in JSON response'):
        required_keys = [
            'jid',
            'tgt',
            'tgt_type',
            'user',
            'fun',
            'arg',
            'kwarg',
            'minions',
            '_stamp',
            'fms_jid_timestamp',
        ]
        for key in response_json:
            assert key in required_keys, f'The response does not contain the key "{key}"'
        attach_json_to_allure(response_json, 'Response JSON')


@allure.feature('Endpoint GET /jobs/{jid}')
@allure.title('Sending a request with a non-existent jid')
def test_get_specific_job_with_non_existent_jid(api):
    jid = 19800803190000000000
    response = api.get(f'/jobs/{jid}')

    with allure.step('Checking that the server has returned the status code == 404'):
        msg = f'Error, the server has returned code {response.status_code}'
        assert response.status_code == 404, msg
    response_json = response.json()
    assert response_json['detail'] == 'Job not found'
    attach_json_to_allure(response_json, 'Response JSON')


@allure.feature('Endpoint GET /jobs/{jid}')
@allure.title('Sending a request with a non-existent and no valid format jid')
def test_get_specific_job_with_non_existent_and_no_valid_format_jid(api):
    jid = 20240999999999999999
    response = api.get(f'/jobs/{jid}')

    with allure.step('Checking that the server has returned the status code == 404'):
        msg = f'Error, the server has returned code {response.status_code}'
        assert response.status_code == 422, msg
    response_json = response.json()
    assert response_json['detail'][0]['msg'] == 'Value error, day is out of range for month'
    attach_json_to_allure(response_json, 'Response JSON')


@allure.feature('Endpoint GET /jobs/{jid}')
@allure.title('Sending a request with a no valid jid')
def test_get_specific_job_with_no_valid_int_jid(api):
    jid = 123
    response = api.get(f'/jobs/{jid}')

    with allure.step('Checking that the server has returned the status code == 422'):
        assert response.status_code == 422, f'Error, the server has returned code {response.status_code}'
    error = response.json()
    check_error_message(error, f'Value error, Jid "{jid}" is not a 20-digits value')
    attach_json_to_allure(error, 'Response JSON')


@allure.feature('Endpoint GET /jobs/{jid}')
@allure.title('Sending a request with a no int jid')
def test_get_specific_job_with_str_type_jid(api):
    jid = 'hello world'
    response = api.get(f'/jobs/{jid}')

    with allure.step('Checking that the server has returned the status code == 422'):
        assert response.status_code == 422, f'Error, the server has returned code {response.status_code}'
    error = response.json()
    check_error_message(error, 'Input should be a valid integer, unable to parse string as an integer')
    attach_json_to_allure(error, 'Response JSON')


@allure.feature('Endpoint POST /jobs')
@allure.title('Sending a valid request with a required parameter')
def test_post_jobs_valid_request(api):
    payload = {
        'tgt': '*',
        'tgt_type': 'glob',
        'fun': 'test.ping',
        'arg': [],
        'kwarg': {},
    }
    response = api.post('/jobs', json=payload)

    with allure.step('Request body'):
        attach_json_to_allure(payload, 'Request payload')

    with allure.step('Checking that the server has returned the status code == 200'):
        assert response.status_code == 200, f'Error, the server has returned code {response.status_code}'
    response_json = response.json()

    with allure.step('Checking that the "jid" was returned in the response'):
        assert 'jid' in response_json.get('return', [])[0], 'Error, "jid" not found in the first element of response'
        jid = response_json['return'][0]['jid']
    with allure.step('Response'):
        attach_json_to_allure(response_json, 'Response JSON')
    time.sleep(0.1)
    REDIS_CLIENT.delete(f'job:{jid}:return')
    delete_job_from_zset_on_redis(jid)


@allure.feature('Endpoint POST /jobs')
@allure.title('Sending a request with a empty JSON')
def test_post_jobs_with_empty_json_body(api):
    payload = {}
    response = api.post('/jobs', json=payload)

    with allure.step('Request body'):
        attach_json_to_allure(payload, 'Request payload')

    with allure.step('Checking that the server has returned the status code == 200'):
        assert response.status_code == 200, f'Error, the server has returned code {response.status_code}'
    response_json = response.json()

    with allure.step('Checking that the "jid" was returned in the response'):
        assert 'jid' in response_json.get('return', [])[0], 'Error, "jid" not found in the first element of response'

    with allure.step('Response'):
        attach_json_to_allure(response_json, 'Response JSON')

    jid = response_json['return'][0]['jid']
    time.sleep(0.1)
    REDIS_CLIENT.delete(f'job:{jid}:return')
    delete_job_from_zset_on_redis(jid)


@allure.feature('Endpoint GET /jobs')
@allure.title('Sending a valid request with a required parameter')
def test_get_jobs(api):
    start_datetime = (datetime.now() - timedelta(hours=4)).isoformat()
    response = api.get(
        '/jobs',
        params={
            'start_datetime': start_datetime,
        },
    )

    with allure.step(f'Required parameter start_datetime = {start_datetime}'):
        pass

    with allure.step('Checking that the server has returned the status code == 200'):
        assert response.status_code == 200, f'Error, the server has returned code {response.status_code}'

    with allure.step('Checking that the all keys was returned in the response'):
        response_json = response.json()
        attach_json_to_allure(response_json, 'Response JSON')
        required_keys = [
            'jid',
            'tgt',
            'tgt_type',
            'user',
            'fun',
            'arg',
            'kwarg',
            'minions',
            '_stamp',
            'fms_jid_timestamp',
        ]
        if response_json:
            for job in response_json:
                for key in job:
                    assert key in required_keys, f'The response does not contain the key "{key}"'
        else:
            pytest.skip('The response came with an empty list/ no jobs')


@allure.feature('Endpoint GET /jobs')
@allure.title('Sending a valid request with all parameter')
def test_get_jobs_with_all_params(api):
    start_datetime = (datetime.now() - timedelta(hours=6)).isoformat()
    end_datetime = (datetime.now()).isoformat()
    response = api.get(
        '/jobs',
        params={
            'start_datetime': start_datetime,
            'end_datetime': end_datetime,
        },
    )

    with allure.step(f'Parameters start_datetime = {start_datetime} and end_datetime = {end_datetime}'):
        pass

    with allure.step('Checking that the server has returned the status code == 200'):
        assert response.status_code == 200, f'Error, the server has returned code {response.status_code}'

    with allure.step('Checking that all keys was returned in the response'):
        response_json = response.json()
        attach_json_to_allure(response_json, 'Response JSON')
        required_keys = [
            'jid',
            'tgt',
            'tgt_type',
            'user',
            'fun',
            'arg',
            'kwarg',
            'minions',
            '_stamp',
            'fms_jid_timestamp',
        ]
        if response_json:
            for job in response_json:
                for key in job:
                    assert key in required_keys, f'The response does not contain the key "{key}"'
        else:
            pytest.skip('The response came with an empty list/ no jobs')


@allure.feature('Endpoint GET /jobs')
@allure.title('Sending no valid request without the required parameter')
def test_get_jobs_with_only_no_required_param(api):
    end_datetime = (datetime.now() - timedelta(hours=4)).isoformat()
    response = api.get(
        '/jobs',
        params={
            'end_datetime': end_datetime,
        },
    )

    with allure.step('Checking that the server has returned the status code == 422'):
        assert response.status_code == 422
    error = response.json()
    check_error_message(error, 'Field required')
    attach_json_to_allure(error, 'Response JSON')


@allure.feature('Endpoint GET /jobs')
@allure.title('Sending a request with a required date parameter set to a future date.')
def test_get_jobs_with_future_date_in_params(api):
    start_datetime = (datetime.now() - timedelta(seconds=3)).isoformat()
    response = api.get('/jobs', params={'start_datetime': start_datetime})

    with allure.step(f'Required parameter start_datetime = {start_datetime}'):
        pass

    with allure.step('Checking that the server has returned the status code == 422'):
        assert response.status_code == 422
    error = response.json()
    check_error_message(error, 'Input should be in the past')
    attach_json_to_allure(error, 'Response JSON')


@allure.feature('Endpoint GET /jobs')
@allure.title('Sending a request with no parameters')
def test_get_jobs_without_params(api):
    response = api.get('/jobs')

    with allure.step('Checking that the server has returned the status code == 422'):
        assert response.status_code == 422
    error = response.json()
    check_error_message(error, 'Field required')
    attach_json_to_allure(error, 'Response JSON')


@allure.feature('Endpoint GET /jobs/{jid}/return')
@allure.title('Sending a GET request to retrieve information about the task results.')
def test_get_info_about_valid_task_return(api, create_jid):
    response = api.get(f'/jobs/{create_jid}/return')

    with allure.step('Checking that the server has returned the status code == 200'):
        assert response.status_code == 200, f'Error, the server has returned code {response.status_code}'
    response_json = response.json()

    with allure.step('Checking that a response includes all required keys'):
        required_keys = [
            'success',
            'retcode',
            'cmd',
            'id',
            'return',
            'jid',
            'fun',
            'fun_args',
            'user',
            '_stamp',
        ]
        for result in response_json['result']:
            for key in required_keys:
                assert key in result, f'The response does not contain the key "{key}"'
        attach_json_to_allure(response_json, 'Response JSON')


@allure.feature('Endpoint GET /jobs/{jid}/return')
@allure.title('Sending a GET request to retrieve information about a task with an invalid jid.')
def test_get_info_about_task_return_with_no_valid_jid(api):
    jid = 2024071
    response = api.get(f'/jobs/{jid}/return')

    with allure.step('Checking that the server has returned the status code == 422'):
        assert response.status_code == 422, f'Error, the server has returned code {response.status_code}'
    error = response.json()
    check_error_message(error, f'Value error, Jid "{jid}" is not a 20-digits value')
    attach_json_to_allure(error, 'Response JSON')


@allure.feature('Endpoint GET /jobs/{jid}/return')
@allure.title('Sending a GET request to retrieve information about a task with a big jid.')
def test_get_info_about_task_return_with_big_jid(api):
    jid = 4000240709134651062132
    response = api.get(f'/jobs/{jid}/return')

    with allure.step('Checking that the server has returned the status code == 422'):
        assert response.status_code == 422, f'Error, the server has returned code {response.status_code}'
    error = response.json()
    check_error_message(error, f'Value error, Jid "{jid}" is not a 20-digits value')
    attach_json_to_allure(error, 'Response JSON')


@allure.feature('Endpoint GET /jobs/{jid}/return')
@allure.title('Sending a GET request to retrieve information about a task with a str jid.')
def test_get_info_about_task_return_with_str_jid(api):
    jid = 'Hello World'
    response = api.get(f'/jobs/{jid}/return')

    with allure.step('Checking that the server has returned the status code == 422'):
        assert response.status_code == 422, f'Error, the server has returned code {response.status_code}'
    error = response.json()
    check_error_message(error, 'Input should be a valid integer, unable to parse string as an integer')
    attach_json_to_allure(error, 'Response JSON')


@allure.feature('Endpoint GET /minion/have_grains')
@allure.title('Sending a GET request to retrieve list of minion id with grains')
def test_get_list_minions_with_grains(api, create_data):
    time.sleep(1)
    response = api.get('/minion/have_grains')
    with allure.step('Checking that the server has returned the status code == 200'):
        assert response.status_code == 200, f'Error, the server has returned code {response.status_code}'

    with allure.step('Checking that a response contains list of minion id'):
        if response.json():
            attach_json_to_allure(response.json(), 'Response JSON')
        else:
            pytest.fail('A response not contains minion id')


@allure.feature('Endpoint GET /minion/{mid}/grains')
@allure.title('Sending a GET request to retrieve minion grains')
def test_get_grains_list_minion(api, create_data):
    mid = create_data[0]
    response = api.get(f'/minion/{mid}/grains')

    with allure.step('Checking that the server has returned the status code == 200'):
        assert response.status_code == 200, f'Error, the server has returned code {response.status_code}'
    response_json = response.json()

    with allure.step('Checking that a response includes all required keys'):
        required_keys = [
            'host',
            'id',
            'os',
            'kernel',
            'master',
        ]
        for key in required_keys:
            assert key in response_json, f'The response does not contain the required key "{key}"'
        attach_json_to_allure(response_json, 'Response JSON')


@allure.feature('Endpoint GET /minion/{mid}/grains')
@allure.title('Sending a GET request with a non-existent minion id')
def test_get_grains_list_no_existent_minion_id(api):
    mid = '3512312555'
    response = api.get(f'/minion/{mid}/grains')

    with allure.step('Checking that the server has returned the status code == 404'):
        assert response.status_code == 404, f'Error, the server has returned code {response.status_code}'
        attach_json_to_allure(response.json(), 'Response JSON')


@allure.feature('Endpoint GET /minion/{mid}/grains')
@allure.title('Sending a GET request with a no valid minion id')
def test_get_grains_list_no_valid_minion_id(api):
    mid = 'Hello world!'
    response = api.get(f'/minion/{mid}/grains')

    with allure.step('Checking that the server has returned the status code == 404'):
        assert response.status_code == 404, f'Error, the server has returned code {response.status_code}'
        attach_json_to_allure(response.json(), 'Response JSON')


@allure.feature('Endpoint GET /minion/{mid}/grain/{grain}')
@allure.title('Checking the received value from Redis with the value received from the API')
def test_get_grain_os_from_minion(api, create_data):
    mid = create_data[-1]

    with allure.step('We retrieve the value of the Redis key and save the value of the OS field'):
        redis_hash_key = f'minion:{mid}:grains'
        value_in_redis = REDIS_CLIENT.hget(redis_hash_key, 'os').decode('UTF-8')
        if not value_in_redis:
            pytest.fail('The value was not received from Redis')
        parsed_value_in_redis = json.loads(value_in_redis)

    with allure.step('Getting the value of the OS field using the API'):
        response = api.get(f'/minion/{mid}/grain/os')

    with allure.step('Checking that the server has returned the status code == 200'):
        assert response.status_code == 200, f'Error, the server has returned code {response.status_code}'

    with allure.step('We compare the values obtained from Redis and via the API and find them to be the same'):
        api_value = response.json()
        if not parsed_value_in_redis == api_value:
            pytest.fail('The value obtained from Redis does not correspond to the value returned by the API')


@allure.feature('Endpoint GET /minion/{mid}/grain/{grain}')
@allure.title('Checking a request for a non-existent field in the redis hash')
def test_get_grain_os_no_contains(api, create_data):
    mid = create_data[-1]

    with allure.step('Getting the value of the no exist field using the API'):
        response = api.get(f'/minion/{mid}/grain/somename')

    with allure.step('Checking that the server has returned the status code == 404'):
        assert response.status_code == 404, f'Error, the server has returned code {response.status_code}'
        attach_json_to_allure(response.json(), 'Response JSON')
