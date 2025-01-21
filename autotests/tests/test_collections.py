from http import HTTPStatus

import pytest

from api.collections_api import get_collection, post_collection, get_collection_cid, put_collection_cid, \
    del_collection_cid
from assertions.assertion_base import assert_status_code, assert_schema
from assertions.minions_assertions import assertion_collection_title
from models.minions_models import CreateCollectionModel
from test_data.valid_no_valid_params import PARAMETERS_FOR_GET_LISTS_ENDPOINTS, BODY_FOR_POST_COLLECTION_ENDPOINT, \
    INVALID_CID_VALUES_FOR_COLLECTION, INVALID_BODY_FOR_PUT_COLLECTION, INVALID_CID_VALUES_FOR_DEL_COLLECTION
from utilities.files_utils import read_json_common_request_data
from utilities.test_data_utils import delete_created_collection


class TestCollections:
    """
     Tests /collections
    """

    # GET /collection
    @pytest.mark.ci
    @pytest.mark.parametrize('page, per_page, expected_status, schema', PARAMETERS_FOR_GET_LISTS_ENDPOINTS)
    def test_get_collections_list(self, api, page, per_page, expected_status, schema):
        response = get_collection(api, page, per_page)
        assert_status_code(response, expected_status)
        assert_schema(response, schema)

    # POST /collection
    @pytest.mark.ci
    @pytest.mark.parametrize('body, expected_status, schema', BODY_FOR_POST_COLLECTION_ENDPOINT)
    def test_post_minions_create_collection(self, api, body, expected_status, schema):
        response = post_collection(api, json=body)
        assert_status_code(response, expected_status)
        assert_schema(response, schema)
        delete_created_collection(api, response)


    # GET /collection/{cid}
    def test_get_collection_valid_cid(self, api, create_cid):
        response = get_collection_cid(api, create_cid)
        assert_status_code(response, HTTPStatus.OK)
        assert_schema(response, CreateCollectionModel)

    # GET /collection/{cid} invalid cid values
    @pytest.mark.parametrize('cid, expected_status, schema', INVALID_CID_VALUES_FOR_COLLECTION)
    def test_get_collection_invalid_cid(self, api, cid, expected_status, schema):
        response = get_collection_cid(api, cid)
        assert_status_code(response, expected_status)
        assert_schema(response, schema)

    # PUT minions/collection/{cid} positive case
    def test_put_minions_collection_valid_cid(self, api, create_cid):
        json_obj = read_json_common_request_data('put_body_for_minions_collection')
        response = put_collection_cid(api, create_cid, json=json_obj)
        assert_status_code(response, HTTPStatus.OK)
        assert_schema(response, CreateCollectionModel)
        assertion_collection_title(api, response, create_cid)

    # PUT /collection/{cid} negative cases
    # Invalid body in request
    @pytest.mark.parametrize('body, expected_status, schema', INVALID_BODY_FOR_PUT_COLLECTION)
    def test_put_minions_collection_invalid_body(self, api, create_cid, body, expected_status, schema):
        response = put_collection_cid(api, create_cid, json=body)
        assert_status_code(response, expected_status)
        assert_schema(response, schema)

    # Invalid cid in request
    @pytest.mark.parametrize('cid, expected_status, schema', INVALID_CID_VALUES_FOR_COLLECTION)
    def test_put_minions_collection_invalid_cid(self, api, cid, expected_status, schema):
        response = put_collection_cid(api, cid, json={'title': 'test'})
        assert_status_code(response, expected_status)
        assert_schema(response, schema)

    # DEL /collection/{cid} positive case
    def test_del_minions_collection_cid(self, api):
        json_obj = read_json_common_request_data('create_collection_for_del')
        created_cid = post_collection(api, json=json_obj).json().get('id')
        response = del_collection_cid(api, created_cid)
        assert_status_code(response, HTTPStatus.NO_CONTENT)
        check_del_collection = get_collection_cid(api, created_cid)
        assert_status_code(check_del_collection, HTTPStatus.NOT_FOUND)

    # DEL /collection/{cid} negative cases
    # Invalid cid in request
    @pytest.mark.parametrize('cid, expected_code', INVALID_CID_VALUES_FOR_DEL_COLLECTION)
    def test_del_minions_collection_invalid_cid(self, api, cid, expected_code):
        response = del_collection_cid(api, cid)
        assert_status_code(response, expected_code)
