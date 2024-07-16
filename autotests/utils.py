import json
import allure


def attach_json_to_allure(data, name):
    """
    Attaching the JSON response from the server to the allure step.

    :param data: The JSON response from the server
    :param name: File name in to allure step
    """
    allure.attach(json.dumps(data, indent=4), name=name, attachment_type=allure.attachment_type.JSON)


def check_error_message(response_json, expected_message):
    """
    Checks if the error message in the response JSON matches the expected message.

    :param response_json: The JSON response from the server
    :param expected_message: The expected error message
    """
    text = f'Checking that the server has returned an error message: "{expected_message}"'
    detail_message = response_json['detail'][0]['msg']
    exception_text = f'Expected message: "{expected_message}", but got: "{detail_message}"'
    with allure.step(text):
        assert detail_message == expected_message, exception_text
