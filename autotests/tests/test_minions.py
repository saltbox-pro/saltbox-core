from http import HTTPStatus

import pytest

from api.minions_api import get_minions_filter_schema, get_minions_mid, post_minions
from assertions.assertion_base import assert_status_code, assert_schema
from models.minions_models import ModelItem
from test_data.valid_no_valid_params import PARAMETERS_FOR_MINIONS_ENDPOINT, INVALID_MID_VALUES


class TestMinions:
    """
    Tests /minions
    """

    def test_get_minions_filter_schema(self, api):
        response = get_minions_filter_schema(api)
        assert_status_code(response, HTTPStatus.OK)
        assert_schema(response, ModelItem)

    @pytest.mark.parametrize('body, expected_status, schema', PARAMETERS_FOR_MINIONS_ENDPOINT)
    def test_get_minions(self, api, create_minions_data, body, expected_status, schema):
        response = post_minions(api, json=body)
        assert_status_code(response, expected_status)
        assert_schema(response, schema)

    # def test_get_minion_mid(self, api, create_minions_data):
    #     response = get_minions_mid(api, create_minions_data[0])
    #     assert_status_code(response, HTTPStatus.OK)
    #     assert_schema(response, MinionModel)

    @pytest.mark.parametrize('mid, expected_status, schema', INVALID_MID_VALUES)
    def test_get_minion_invalid_mid(self, api, mid, expected_status, schema):
        response = get_minions_mid(api, mid)
        assert_status_code(response, expected_status)
        assert_schema(response, schema)
