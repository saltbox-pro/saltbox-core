import pytest

from api.tasks_api import get_tasks_template, post_tasks_template
from assertions.assertion_base import assert_status_code, assert_schema
from test_data.valid_no_valid_params import PARAMETERS_FOR_GET_LISTS_ENDPOINTS, BODY_FOR_POST_TASKS_TEMPLATE_ENDPOINT


class TestTasks:
    """
    Tests /tasks
    """

    @pytest.mark.parametrize('page, per_page, expected_status, schema', PARAMETERS_FOR_GET_LISTS_ENDPOINTS)
    def test_get_tasks_template_list(self, api, page, per_page, expected_status, schema):
        response = get_tasks_template(api, page, per_page)
        assert_status_code(response, expected_status)
        assert_schema(response, schema)

    @pytest.mark.parametrize('body, expected_status, schema', BODY_FOR_POST_TASKS_TEMPLATE_ENDPOINT)
    def test_post_tasks_template(self, api, body, expected_status, schema):
        response = post_tasks_template(api, json=body)
        assert_status_code(response, expected_status)
        assert_schema(response, schema)
