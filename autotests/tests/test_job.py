import asyncio
import pytest

from http import HTTPStatus
from api.jobs_api import get_jobs, get_jobs_jid, ws_jobs, post_jobs, get_jobs_jid_return, get_jobs_jid_returns_count, \
    ws_jobs_return
from assertions.assertion_base import assert_status_code, assert_schema, \
    assert_not_found, assert_unprocessable_entity
from assertions.jobs_assertion import assert_jid_in_response, assert_count
from assertions.ws_assertion import wait_for_job_message
from models.jobs_models import Jobs, ModelJobResponse, ModelJobReturn
from test_data.valid_no_valid_params import (VALID_AND_INVALID_PARAMS_FOR_JOBS, INVALID_JID,
                                             INVALID_QUERY_PARAMS_FOR_JOB_RETURN)
from utilities.test_data_utils import create_new_job, delete_created_data, create_sleep_job


class TestJobs:
    """
    Tests /jobs
    """
    # GET /jobs endpoint
    @pytest.mark.ci
    @pytest.mark.parametrize('start_datetime, end_datetime, expected_status, schema', VALID_AND_INVALID_PARAMS_FOR_JOBS)
    def test_get_jobs(self, api, start_datetime, end_datetime, expected_status, schema):
        response = get_jobs(api, start_datetime, end_datetime)
        assert_status_code(response, expected_status)
        assert_schema(response, schema)

    # GET /jobs/{jid} endpoint
    @pytest.mark.ci
    def test_get_jobs_jid(self, api, create_jid):
        jid = create_jid
        response = get_jobs_jid(api, jid)
        assert_status_code(response, HTTPStatus.OK)
        assert_schema(response, Jobs)
        assert_jid_in_response(jid, response)

    @pytest.mark.ci
    def test_get_jobs_no_exist_jid(self, api, request):
        jid = 19800803190000000000
        response = get_jobs_jid(api, jid)
        assert_status_code(response, HTTPStatus.NOT_FOUND)
        assert_not_found(request, response)

    @pytest.mark.ci
    @pytest.mark.parametrize('jid, expected_status, type_of_error', INVALID_JID)
    def test_get_jobs_no_valid_jid(self, request, api, jid, expected_status, type_of_error):
        response = get_jobs_jid(api, jid)
        assert_status_code(response, expected_status)
        assert_unprocessable_entity(request, response, type_of_error)

    # WS /jobs endpoint
    @pytest.mark.ci
    @pytest.mark.asyncio
    async def test_ws_jobs(self, api):
        await ws_jobs(api)
        jid = create_new_job(api)
        await wait_for_job_message(api, jid)
        await api.ws.close()
        delete_created_data(jid)

    @pytest.mark.asyncio
    async def test_ws_jobs_return(self, api):
        jid = create_sleep_job(api)
        await ws_jobs_return(api, jid)
        await wait_for_job_message(api, jid)
        await api.ws.close()
        delete_created_data(jid)

    # GET /jobs/{jid}/return endpoint
    @pytest.mark.ci
    def test_get_jobs_return(self, api, create_jid):
        response = get_jobs_jid_return(api, create_jid)
        assert_status_code(response, HTTPStatus.OK)
        assert_schema(response, ModelJobReturn)

    @pytest.mark.ci
    @pytest.mark.parametrize('jid, expected_status, type_of_error', INVALID_JID)
    def test_get_jobs_return_no_valid_jid(self, request, api, jid, expected_status, type_of_error):
        response = get_jobs_jid_return(api, jid)
        assert_status_code(response, expected_status)
        assert_unprocessable_entity(request, response, type_of_error)

    # GET /jobs/{jid}/return endpoint with params
    @pytest.mark.ci
    def test_get_jobs_return_query_count(self, api, create_jid):
        count_param = 2
        response = get_jobs_jid_return(api, create_jid, count_param)
        assert len(response.json()['result']) >= count_param

    @pytest.mark.ci
    @pytest.mark.parametrize('count, cursor, expected_status, type_of_error', INVALID_QUERY_PARAMS_FOR_JOB_RETURN)
    def test_get_jobs_rtn_query_params(self, request, api, create_jid, count, cursor, expected_status, type_of_error):
        response = get_jobs_jid_return(api, create_jid, count, cursor)
        assert_status_code(response, expected_status)
        assert_unprocessable_entity(request, response, type_of_error)

    # GET /jobs/returns-count endpoint
    @pytest.mark.ci
    def test_get_jobs_return_count(self, api, create_jid):
        response = get_jobs_jid_returns_count(api, create_jid)
        assert_status_code(response, HTTPStatus.OK)
        assert_count(api, response, create_jid)

    # POST /jobs endpoint
    @pytest.mark.ci
    def test_post_jobs_empty_body(self, api, request):
        post_obj = None
        response = post_jobs(api, json=post_obj)
        assert_status_code(response, HTTPStatus.UNPROCESSABLE_ENTITY)
        assert_unprocessable_entity(request, response, 'invalid_body')

    @pytest.mark.ci
    def test_post_jobs_empty_json(self, api):
        response = post_jobs(api, json={})
        jid = response.json()['return'][0]['jid']
        assert_status_code(response, HTTPStatus.OK)
        assert_schema(response, ModelJobResponse)
        delete_created_data(jid)
