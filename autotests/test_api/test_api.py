import pytest
from datetime import datetime, timedelta
import allure

from utils import attach_json_to_allure, check_error_message


@allure.feature('Endpoint GET /jobs/{jid}')
@allure.title('Sending a valid request to receive a specific job')
def test_get_specific_job(api, create_jid):
    response = api.get(f'/jobs/{create_jid}')
    with allure.step('Checking that the server has returned the status code == 200'):
        assert response.status_code == 200, f'Error, the server has returned code {response.status_code}'
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
    jid = 20240999999999999999
    response = api.get(f'/jobs/{jid}')
    with allure.step('Checking that the server has returned the status code == 404'):
        assert response.status_code == 404, f'Error, the server has returned code {response.status_code}'
    response_json = response.json()
    assert response_json['detail'] == 'Job not found'
    attach_json_to_allure(response_json, 'Response JSON')


@allure.feature('Endpoint GET /jobs/{jid}')
@allure.title('Sending a request with a no valid jid')
def test_get_specific_job_with_no_valid_int_jid(api):
    jid = 123
    response = api.get(f'/jobs/{jid}')
    with allure.step('Checking that the server has returned the status code == 422'):
        assert response.status_code == 422, f'Error, the server has returned code {response.status_code}'
    error = response.json()
    check_error_message(error, 'Input should be greater than 19700000000000000000')
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
        'fun': 'test_api.ring',
        'arg': [],
        'kwarg': {}
    }
    response = api.post('/jobs', json=payload)
    with allure.step('Request body'):
        attach_json_to_allure(payload, 'Request payload')

    with allure.step('Checking that the server has returned the status code == 200'):
        assert response.status_code == 200, f'Error, the server has returned code {response.status_code}'
    response_json = response.json()
    with allure.step('Checking that the "jid" was returned in the response'):
        assert any('jid' in item for item in response_json.get('return', []))
    with allure.step('Response'):
        attach_json_to_allure(response_json, 'Response JSON')


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
        assert any('jid' in item for item in response_json.get('return', []))
    with allure.step('Response'):
        attach_json_to_allure(response_json, 'Response JSON')


@allure.feature('Endpoint GET /jobs')
@allure.title('Sending a valid request with a required parameter')
def test_get_jobs(api):
    start_datetime = (datetime.now() - timedelta(hours=4)).isoformat()
    response = api.get(
        '/jobs',
        params={
            'start_datetime': start_datetime,
        })
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
    end_datetime = (datetime.now() - timedelta(hours=4)).isoformat()

    response = api.get(
        '/jobs',
        params={
            'start_datetime': start_datetime,
            'end_datetime': end_datetime,
        })
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
        })
    with allure.step('Checking that the server has returned the status code == 422'):
        assert response.status_code == 422
    error = response.json()
    check_error_message(error, 'Field required')
    attach_json_to_allure(error, 'Response JSON')


@allure.feature('Endpoint GET /jobs')
@allure.title('Sending a request with a required date parameter set to a future date.')
def test_get_jobs_with_future_date_in_params(api):
    start_datetime = (datetime.now() - timedelta(seconds=3)).isoformat()
    response = api.get(
        '/jobs',
        params={
            'start_datetime': start_datetime
        })
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


@allure.feature('Endpoint GET /jobs/{jid}/rets')
@allure.title('Sending a GET request to retrieve information about the task results.')
def test_get_info_about_valid_task_rets(api, create_jid):
    response = api.get(f'/jobs/{create_jid}/rets')
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
            '_stamp'
        ]
        for result in response_json:
            for key in required_keys:
                assert key in result, f'The response does not contain the key "{key}"'
        attach_json_to_allure(response_json, 'Response JSON')


@allure.feature('Endpoint GET /jobs/{jid}/rets')
@allure.title('Sending a GET request to retrieve information about a task with an invalid jid.')
def test_get_info_about_task_rets_with_no_valid_jid(api):
    jid = 2024071
    response = api.get(f'/jobs/{jid}/rets')
    with allure.step('Checking that the server has returned the status code == 422'):
        assert response.status_code == 422, f'Error, the server has returned code {response.status_code}'
    error = response.json()
    check_error_message(error, 'Input should be greater than 19700000000000000000')
    attach_json_to_allure(error, 'Response JSON')


@allure.feature('Endpoint GET /jobs/{jid}/rets')
@allure.title('Sending a GET request to retrieve information about a task with a big jid.')
def test_get_info_about_task_rets_with_big_jid(api):
    jid = 4000240709134651062132
    response = api.get(f'/jobs/{jid}/rets')
    with allure.step('Checking that the server has returned the status code == 422'):
        assert response.status_code == 422, f'Error, the server has returned code {response.status_code}'
    error = response.json()
    check_error_message(error, 'Input should be less than 100000000000000000000')
    attach_json_to_allure(error, 'Response JSON')


@allure.feature('Endpoint GET /jobs/{jid}/rets')
@allure.title('Sending a GET request to retrieve information about a task with a str jid.')
def test_get_info_about_task_rets_with_str_jid(api):
    jid = 'Hello World'
    response = api.get(f'/jobs/{jid}/rets')
    with allure.step('Checking that the server has returned the status code == 422'):
        assert response.status_code == 422, f'Error, the server has returned code {response.status_code}'
    error = response.json()
    check_error_message(error, 'Input should be a valid integer, unable to parse string as an integer')
    attach_json_to_allure(error, 'Response JSON')
