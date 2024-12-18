import pytest

from http import HTTPStatus
from api.minions_api import get_minions_filter_schema, get_minions_mid, post_minions, get_minions_collection, \
    post_minions_collection, post_minions_filter_values, get_minion_collection_cid, put_minion_collection_cid, \
    del_minion_collection_cid
from assertions.assertion_base import assert_status_code, assert_schema
from assertions.minions_assertions import assertion_collection_title
from models.minions_models import ModelItem, MinionModel, CreateCollectionModel
from test_data.valid_no_valid_params import BODY_FOR_POST_MINIONS_ENDPOINT, INVALID_MID_VALUES, \
    PARAMETERS_FOR_GET_MINIONS_COLLECTION_ENDPOINT, BODY_FOR_POST_MINIONS_COLLECTION_ENDPOINT, \
    BODY_FOR_POST_MINIONS_FILTER, INVALID_BODY_FOR_PUT_MINIONS_COLLECTION, \
    INVALID_CID_VALUES_FOR_MINIONS_COLLECTION, INVALID_CID_VALUES_FOR_DEL_MINIONS_COLLECTION
from utilities.files_utils import read_json_common_request_data


class TestMinions:
    """
    Tests /minions
    """

    @pytest.mark.ci
    # GET /minions/filter_schema endpoint
    def test_get_minions_filter_schema(self, api):
        response = get_minions_filter_schema(api)
        assert_status_code(response, HTTPStatus.OK)
        assert_schema(response, ModelItem)

    # POST /minions/filter-values
    @pytest.mark.ci
    @pytest.mark.parametrize('body, expected_status, schema', BODY_FOR_POST_MINIONS_FILTER)
    def test_post_minions_filter_values(self, api, body, expected_status, schema):
        response = post_minions_filter_values(api, json=body)
        assert_status_code(response, expected_status)
        assert_schema(response, schema)

    # GET minions/collection
    @pytest.mark.ci
    @pytest.mark.parametrize('page, per_page, expected_status, schema', PARAMETERS_FOR_GET_MINIONS_COLLECTION_ENDPOINT)
    def test_get_minions_collections_list(self, api, page, per_page, expected_status, schema):
        response = get_minions_collection(api, page, per_page)
        assert_status_code(response, expected_status)
        assert_schema(response, schema)

    # POST minions/collection
    @pytest.mark.ci
    @pytest.mark.parametrize('body, expected_status, schema', BODY_FOR_POST_MINIONS_COLLECTION_ENDPOINT)
    def test_post_minions_create_collection(self, api, body, expected_status, schema):
        response = post_minions_collection(api, json=body)
        assert_status_code(response, expected_status)
        assert_schema(response, schema)

    # GET minions/collection/{cid}
    def test_get_minions_collection_valid_cid(self, api, create_cid):
        response = get_minion_collection_cid(api, create_cid)
        assert_status_code(response, HTTPStatus.OK)
        assert_schema(response, CreateCollectionModel)

    # GET minions/collection/{cid} invalid cid values
    @pytest.mark.parametrize('cid, expected_status, schema', INVALID_CID_VALUES_FOR_MINIONS_COLLECTION)
    def test_get_minions_collection_invalid_cid(self, api, cid, expected_status, schema):
        response = get_minion_collection_cid(api, cid)
        assert_status_code(response, expected_status)
        assert_schema(response, schema)

    # PUT minions/collection/{cid} positive case
    def test_put_minions_collection_valid_cid(self, api, create_cid):
        json_obj = read_json_common_request_data('put_body_for_minions_collection')
        response = put_minion_collection_cid(api, create_cid, json=json_obj)
        assert_status_code(response, HTTPStatus.OK)
        assert_schema(response, CreateCollectionModel)
        assertion_collection_title(api, response, create_cid)

    # PUT minions/collection/{cid} negative cases
    # Invalid body in request
    @pytest.mark.parametrize('body, expected_status, schema', INVALID_BODY_FOR_PUT_MINIONS_COLLECTION)
    def test_put_minions_collection_invalid_body(self, api, create_cid, body, expected_status, schema):
        response = put_minion_collection_cid(api, create_cid, json=body)
        assert_status_code(response, expected_status)
        assert_schema(response, schema)

    # Invalid cid in request
    @pytest.mark.parametrize('cid, expected_status, schema', INVALID_CID_VALUES_FOR_MINIONS_COLLECTION)
    def test_put_minions_collection_invalid_cid(self, api, cid, expected_status, schema):
        response = put_minion_collection_cid(api, cid, json={'title': 'test'})
        assert_status_code(response, expected_status)
        assert_schema(response, schema)

    # DEL minions/collection/{cid} positive case
    def test_del_minions_collection_cid(self, api):
        json_obj = read_json_common_request_data('create_collection_for_del')
        created_cid = post_minions_collection(api, json=json_obj).json().get('id')
        response = del_minion_collection_cid(api, created_cid)
        assert_status_code(response, HTTPStatus.NO_CONTENT)
        check_del_collection = get_minion_collection_cid(api, created_cid)
        assert_status_code(check_del_collection, HTTPStatus.NOT_FOUND)

    # DEL minions/collection/{cid} negative cases
    # Invalid cid in request
    @pytest.mark.parametrize('cid, expected_code', INVALID_CID_VALUES_FOR_DEL_MINIONS_COLLECTION)
    def test_del_minions_collection_invalid_cid(self, api, cid, expected_code):
        response = del_minion_collection_cid(api, cid)
        assert_status_code(response, expected_code)

    # POST /minions
    @pytest.mark.ci
    @pytest.mark.parametrize('body, expected_status, schema', BODY_FOR_POST_MINIONS_ENDPOINT)
    def test_post_minions(self, api, create_minions_data, body, expected_status, schema):
        response = post_minions(api, json=body)
        assert_status_code(response, expected_status)
        assert_schema(response, schema)

    # GET minions/{mid} endpoint
    # Positive case
    def test_get_minion_mid(self, api, create_minions_data):
        response = get_minions_mid(api, create_minions_data[0])
        assert_status_code(response, HTTPStatus.OK)
        assert_schema(response, MinionModel)

    # Negative cases
    @pytest.mark.ci
    @pytest.mark.parametrize('mid, expected_status, schema', INVALID_MID_VALUES)
    def test_get_minion_invalid_mid(self, api, mid, expected_status, schema):
        response = get_minions_mid(api, mid)
        assert_status_code(response, expected_status)
        assert_schema(response, schema)
