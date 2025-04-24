import time
from http import HTTPStatus

from api.collections_api import del_collection_cid
from api.jobs_api import post_jobs
from assertions.assertion_base import assert_status_code
from conftest import redis_client
from utilities.files_utils import read_json_common_request_data
from utilities.redis_utils import delete_job_from_zset_on_redis


def create_new_job(api):
    post_obj = read_json_common_request_data('valid_post_jobs')
    response = post_jobs(api, json=post_obj)
    assert_status_code(response, HTTPStatus.OK)
    jid = response.json().get('jid')
    return jid


def create_sleep_job(api):
    post_obj = read_json_common_request_data('valid_post_sleep_jobs')
    response = post_jobs(api, json=post_obj)
    assert_status_code(response, HTTPStatus.OK)
    jid = response.json().get('jid')
    return jid


def delete_created_data(jid):
    time.sleep(0.2)
    redis_client.delete(f'job:{jid}:return')
    delete_job_from_zset_on_redis(jid)


def delete_created_collection(api, response):
    collection_id = response.json().get('id')
    del_collection_cid(api, collection_id)
