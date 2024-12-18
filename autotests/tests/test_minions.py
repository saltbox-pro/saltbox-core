import pytest

from http import HTTPStatus
from api.minions_api import get_minions_mid, post_minions
from assertions.assertion_base import assert_status_code, assert_schema
from models.minions_models import MinionModel
from test_data.valid_no_valid_params import BODY_FOR_POST_MINIONS_ENDPOINT, INVALID_MID_VALUES


class TestMinions:
    """
    Tests /minions
    """

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
