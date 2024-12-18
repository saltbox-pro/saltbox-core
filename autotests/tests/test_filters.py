import pytest

from http import HTTPStatus
from api.filters_api import get_filter_schema, post_filter_values
from assertions.assertion_base import assert_status_code, assert_schema
from models.filters_models import FilterSchemaModel
from test_data.valid_no_valid_params import BODY_FOR_POST_FILTER


class TestFilters:
    """
    Tests /filters
    """

    # GET /minions/filter_schema endpoint
    @pytest.mark.ci
    def test_get_filter_schema(self, api):
        response = get_filter_schema(api)
        assert_status_code(response, HTTPStatus.OK)
        assert_schema(response, FilterSchemaModel)

    # POST /minions/filter-values
    @pytest.mark.ci
    @pytest.mark.parametrize('body, expected_status, schema', BODY_FOR_POST_FILTER)
    def test_post_filter_values(self, api, body, expected_status, schema):
        response = post_filter_values(api, json=body)
        assert_status_code(response, expected_status)
        assert_schema(response, schema)
