import json
import time
import pytest
import allure  # type: ignore


def attach_json_to_allure(data, name):
    """
    Attaching the JSON response from the server to the allure step.

    :param data: The JSON response from the server.
    :param name: File name in to allure step.
    """
    allure.attach(
        json.dumps(data, indent=4),
        name=name,
        attachment_type=allure.attachment_type.JSON,
    )


def check_error_message(response_json, expected_message):
    """
    Checks if the error message in the response JSON matches the expected message.

    :param response_json: The JSON response from the server.
    :param expected_message: The expected error message.
    """
    text = f'Checking that the server has returned an error message: "{expected_message}"'
    detail_message = response_json['detail'][0]['msg']
    exception_text = f'Expected message: "{expected_message}", but got: "{detail_message}"'
    with allure.step(text):
        assert detail_message == expected_message, exception_text


def create_new_job(api):
    """
    This function for create test.ping job and get actual jid.
    """
    payload = {
        'tgt': '*',
        'tgt_type': 'glob',
        'fun': 'test.ping',
        'arg': [],
        'kwarg': {},
    }
    response_json = api.post('/jobs', json=payload).json()
    jid = response_json['return'][0]['jid']
    return jid


def get_available_minion(api):
    """
    This function for get available minion for creating job.
    """
    payload = {
        'tgt': '*',
        'tgt_type': 'glob',
        'fun': 'test.ping',
        'arg': [],
        'kwarg': {},
    }
    response_json = api.post('/jobs', json=payload).json()
    if not response_json:
        pytest.fail('Received an empty response')
    jid = response_json['return'][0]['jid']
    time.sleep(0.5)
    actual_response = api.get(f'/jobs/{jid}/return').json()
    if not actual_response:
        pytest.fail('Received an empty response')
    available_minion = actual_response[0]['id']
    if not available_minion:
        pytest.fail('No available minions found.')
    else:
        return available_minion


def create_sleep_job(api):
    """
    This function for create test.sleep job and get actual jid.
    """
    available_minion = get_available_minion(api)
    payload = {
        'tgt': available_minion,
        'tgt_type': 'glob',
        'fun': 'test.sleep',
        'arg': ['0,5'],
        'kwarg': {},
    }
    response_json = api.post('/jobs', json=payload).json()
    if not response_json:
        pytest.fail('Received an empty response')
    jid = response_json['return'][0]['jid']
    if not jid:
        pytest.fail('JID is not available')
    return jid
