from typing import Type

from pydantic import BaseModel

from utilities.files_utils import read_json_test_data, read_json_common_response_data
from utilities.json_utils import compare_json_left_in_right


class LogMsg:
    """
    A base class for constructing AssertionError logs. It builds the message in its _msg field.
    """

    def __init__(self, where, response):
        self._msg = ''
        self._response = response
        self._where = where

    def add_request_url(self):
        """
        Adds data about the request sent to the server.
        """
        self._msg += (
            f'Request content (url, query params, тело):\n'
            f'\tURL: {self._response.request.url}\n'
        )
        self._msg += f'\tmethod: {self._response.request.method}\n'
        self._msg += f'\theaders: {dict(self._response.request.headers)}\n'
        if hasattr(self._response.request, 'params'):
            self._msg += f'\tquery params: {self._response.request.params}\n'
        else:
            self._msg += '\tquery params:\n'
        if hasattr(self._response.request, 'content') and self._response.request.read():
            self._msg += f'\tbody: {self._response.request.read()}\n'
        else:
            self._msg += '\tbody:\n'
        return self

    def add_response_info(self):
        """
        Adds information about the content of the response body.
        """
        self._msg += f'Response body:\n\t{self._response.content}\n'
        return self

    def add_error_info(self, text):
        if text:
            self._msg += f'\n{text}\n'
        else:
            self._msg += '\n'
        return self

    def get_message(self):
        return self._msg


class BodyLogMsg(LogMsg):
    """
    Adds the results of response body checks to the logs.
    """

    def __init__(self, response):
        super().__init__('IN RESPONSE BODY', response)

    def add_compare_result(self, diff):
        """
        Adds information about the result of comparing the received JSON with the reference.
        :param diff: dictionary with field data that has different values after comparison.
        """

        self._msg += f'{self._where} in JSON, the following fields did not match the reference\n'
        for key, value in diff.items():
            self._msg += f'key: {value["path"]}\n\t\texpected: {value["expected"]} \n\t\tactual: {value["actual"]}\n'
        return self


class CodeLogMsg(LogMsg):
    """
    Adds the results of response code checks to the logs.
    """

    def __init__(self, response):
        super().__init__('IN RESPONSE CODE', response)

    def add_compare_result(self, exp, act):
        """
        Adds information about the expected and actual response code.
        :param exp: expected code
        :param act: actual code
        """

        self._msg += f'{self._where} \n\texpected code: {exp}\n\treceived code: {act}\n'
        return self


class BodyValueLogMsg(LogMsg):
    def __init__(self, response):
        super().__init__('IN RESPONSE BODY', response)

    def add_compare_result(self, exp, act):
        """
        Adds information about value comparison in the response body.
        :param exp: expected value
        :param act: actual value
        """

        self._msg += f'\texpected: {exp}\n\tactual: {act}\n'
        return self


def assert_status_code(response, expected_code):
    """
    Compares the server response code with the expected code.
    :param response: response received from the server
    :param expected_code: expected response code
    :raises AssertionError: if the values do not match
    """

    assert expected_code == response.status_code, CodeLogMsg(response) \
        .add_compare_result(expected_code, response.status_code) \
        .add_request_url() \
        .add_response_info() \
        .get_message()


def assert_schema(response, model: Type[BaseModel]):
    """
    Checks the response body against its schema using Pydantic.
    :param response: response from the server
    :param model: model to validate the JSON schema
    :raises ValidationError: if the response body does not match the schema
    """
    if model:
        body = response.json()
        if isinstance(body, list):
            for item in body:
                model.model_validate(item, strict=True)
        else:
            model.model_validate(body, strict=True)


def assert_left_in_right_json(response, exp_json, actual_json):
    """
    Checks that all field values in `exp_json` match the field values in `actual_json`.
    :param response: response received from the server
    :param exp_json: expected reference JSON
    :param actual_json: received JSON
    :raises AssertionError: if `exp_json` has fields with mismatched or missing values in `actual_json`
    """
    root = 'root:' if isinstance(actual_json, list) else ''
    compare_res = compare_json_left_in_right(exp_json, actual_json, key=root, path=root)
    assert not compare_res, BodyLogMsg(response) \
        .add_compare_result(compare_res) \
        .add_request_url() \
        .add_response_info() \
        .get_message()


def assert_response_body_fields(request, response, exp_obj=None):
    """
    Checks the server response by comparing the expected object with the received one.
    :param request: standard `request` object from the pytest framework
    :param response: response from the server
    :param exp_obj: expected object
    """
    exp_json = read_json_test_data(request) if exp_obj is None else exp_obj
    act_json = response.json()
    assert_left_in_right_json(response, exp_json, act_json)


def assert_response_body_value(response, exp, act, text=None):
    """
    Checks the server response by comparing the received value with the expected one in the request body.
    :param response: response from the server
    :param exp: expected value
    :param act: received value
    :param text: additional text to display if `exp` and `act` do not match
    """
    assert exp == act, BodyValueLogMsg(response) \
        .add_error_info(text) \
        .add_compare_result(exp, act) \
        .add_request_url() \
        .add_response_info() \
        .get_message()


def assert_empty_list(response):
    """
    Checks that the response body contains an empty list.
    :param response: response from the server
    """
    assert_left_in_right_json(response, [], response.json())


def assert_bad_request(request, response):
    """
    Checks that the response body contains BAD REQUEST data.
    :param request: standard `request` object from the pytest framework
    :param response: response from the server
    """
    assert_response_body_fields(request, response, exp_obj=read_json_common_response_data("bad_request_response"))


def assert_unprocessable_entity(request, response, type_of_error):
    """
    Checks that the response body contains UNPROCESSABLE ENTITY data.
    :param request: standard `request` object from the pytest framework
    :param response: response from the server
    :param type_of_error: reference JSON file for comparing the response
    """
    if type_of_error:
        typs_of_errors = {
            'invalid_day_value': 'no_valid_day_jid_response',
            'invalid_int_value': 'no_valid_int_jid_response',
            'invalid_str_value': 'no_valid_str_jid_response',
            'invalid_body': 'empty_body_error_response',
            'negative_num_value': 'negative_count_number_in_params',
            'invalid_str_count': 'invalid_count_param_str'

        }
        exp = read_json_common_response_data(typs_of_errors.get(type_of_error, 'no_valid_str_jid_response'))
        assert_response_body_fields(request, response, exp_obj=exp)


def assert_not_found(request, response):
    """
    Checks that the response body contains NOT FOUND data.
    :param request: standard `request` object from the pytest framework
    :param response: response from the server
    """
    exp = read_json_common_response_data('not_found_job_response')
    assert_response_body_fields(request, response, exp_obj=exp)


def assert_not_exist(request, response, obj_id):
    """
    Checks that the response body contains NOT EXIST data.
    :param request: standard `request` object from the pytest framework
    :param response: response from the server
    :param obj_id: ID of the object not found by the server
    """
    exp = read_json_test_data(request)
    exp['error'] = exp['error'].format(obj_id)
    assert_response_body_fields(request, response, exp_obj=exp)
