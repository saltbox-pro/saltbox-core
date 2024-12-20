import logging
import os
import time
import pytest

from http import HTTPStatus
from dotenv import load_dotenv
from api.api_client import ApiClient
from api.collections_api import post_collection, del_collection_cid
from api.jobs_api import post_jobs
from api.minions_api import post_minions
from assertions.assertion_base import assert_status_code, assert_schema
from utilities.files_utils import read_json_common_request_data
from utilities.logger_utils import logger
from utilities.redis_utils import redis_client, delete_job_from_zset_on_redis


def pytest_configure(config):
    # Set the current directory to the project root (this allows for relative file paths)
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    # Load environment variables from the /.env file
    load_dotenv(dotenv_path='.env')

    # Set up logger parameters
    path = 'logs/'
    os.makedirs(os.path.dirname(path), exist_ok=True)
    file_handler = logging.FileHandler(path + 'info.log', 'w')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter('%(lineno)d: %(asctime)s %(message)s'))

    # Create custom logger
    custom_logger = logging.getLogger('custom_logger')
    custom_logger.setLevel(logging.INFO)
    custom_logger.addHandler(file_handler)


def pytest_runtest_setup(item):
    logger.info(f'{item.name}:')


@pytest.fixture(scope='class')
def api():
    return ApiClient()


@pytest.fixture(scope='class')
def create_jid(api):
    post_obj = read_json_common_request_data('valid_post_jobs')
    response = post_jobs(api, json=post_obj)
    assert_status_code(response, HTTPStatus.OK)
    jid = response.json().get('jid')
    yield jid
    time.sleep(0.1)
    redis_client.delete(f'job:{jid}:return')
    delete_job_from_zset_on_redis(jid)


@pytest.fixture(scope='class')
def create_minions_data(api):
    post_obj = read_json_common_request_data('grains_items_post')
    response = post_jobs(api, json=post_obj)
    jid = response.json().get('jid')
    assert_status_code(response, HTTPStatus.OK)
    response_minions_list = post_minions(api, json={})
    id_list = [item['_id'] for item in response_minions_list.json()['data']]
    mid_list = [item['minion_id'] for item in response_minions_list.json()['data']]
    yield id_list
    redis_client.delete(f'job:{jid}:return')
    delete_job_from_zset_on_redis(jid)
    for i in mid_list:
        redis_client.delete(f'minion:{i}:grains')


@pytest.fixture(scope='class')
def create_cid(api):
    post_obj = read_json_common_request_data('create_collection_for_fixture')
    response = post_collection(api, json=post_obj)
    assert_status_code(response, HTTPStatus.OK)
    cid = response.json().get('id')
    yield cid
    del_collection_cid(api, cid)
