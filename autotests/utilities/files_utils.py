import json


def get_test_data_path():
    """
    Returns the path to the test data directory.
    """
    return "test_data"


def get_common_response_path():
    """
    Returns the path to the common response directory.
    """
    return f"{get_test_data_path()}/common/responses"


def get_common_requests_path():
    """
    Returns the path to the common requests directory.
    """
    return f"{get_test_data_path()}/common/requests"


def read_json_file_data(path):
    """
    Reads the content of a JSON file and returns it as a dictionary.
    :param path: Path to the file without the `.json` extension.
    :return: The contents of the JSON file as a dictionary.
    """
    with open(f"{path}.json", "r") as f:
        data = json.load(f)
    return data


def read_json_test_data(request):
    """
    Reads test data in JSON format for a specific test.
    :param request: The standard `request` object from the pytest framework.
    :return: The contents of the test data file from the `test_data` directory.
    """
    return read_json_file_data(f"{get_test_data_path()}/{request.node.originalname}")


def read_json_common_response_data(file_name):
    """
    Reads common test response data in JSON format.
    :param file_name: The name of the file without the `.json` extension.
    :return: The contents of the file from the `test_data/common/responses` directory.
    """
    return read_json_file_data(f"{get_common_response_path()}/{file_name}")


def read_json_common_request_data(file_name):
    """
    Reads common test request data in JSON format.
    :param file_name: The name of the file without the `.json` extension.
    :return: The contents of the file from the `test_data/common/requests` directory.
    """
    return read_json_file_data(f"{get_common_requests_path()}/{file_name}")
