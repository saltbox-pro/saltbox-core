from datetime import timedelta, datetime
from http import HTTPStatus

from models.errors_models import ErrorResponse, NotFoundModel
from models.jobs_models import Jobs
from models.minions_models import MinionsListModel, CollectionsListModel

VALID_AND_INVALID_PARAMS_FOR_JOBS = [
    # Valid params
    ((datetime.now() - timedelta(hours=4)).isoformat(), None, HTTPStatus.OK, Jobs),  # Only start_datetime
    ((datetime.now() - timedelta(hours=4)).isoformat(), datetime.now().isoformat(), HTTPStatus.OK, Jobs),  # Valid range
    (datetime.now().isoformat(), datetime.now().isoformat(), HTTPStatus.OK, Jobs),  # start_datetime == end_datetime

    # Boundary and invalid cases
    ((datetime.now() - timedelta(minutes=1)).isoformat(), (datetime.now() - timedelta(minutes=2)).isoformat(),
     HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),  # end_datetime < start_datetime

    # Invalid format
    ('invalid_date', None, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),  # Invalid start_datetime format
    (None, 'invalid_date', HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),  # Invalid end_datetime format
    (' ', None, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),  # Empty start_datetime
    (None, ' ', HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),  # Empty end_datetime

    # Missing params
    (None, None, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),  # Missing both params
    (None, datetime.now().isoformat(), HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),  # Missing start_datetime

    # Future dates
    ('2100-10-28T16:53:20.841870', None, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),  # Future start_datetime
    # ((datetime.now() - timedelta(hours=4)).isoformat(), '2100-10-28T16:53:20.841870', HTTPStatus.UNPROCESSABLE_ENTITY,
    #  ErrorResponse),  # Future end_datetime

    # Edge cases
    ('1970-01-01T00:00:00Z', None, HTTPStatus.OK, Jobs),  # Unix epoch as start_datetime
    ('1970-01-01T00:00:00Z', '1970-01-01T00:01:00Z', HTTPStatus.OK, Jobs),  # Minimum range from epoch
]


INVALID_JID = [
    (20240999999999999999, HTTPStatus.UNPROCESSABLE_ENTITY, 'invalid_day_value'),
    (123, HTTPStatus.UNPROCESSABLE_ENTITY, 'invalid_int_value'),
    ('hello world', HTTPStatus.UNPROCESSABLE_ENTITY, 'invalid_str_value'),
]


INVALID_QUERY_PARAMS_FOR_JOB_RETURN = [
    (-1, 0, HTTPStatus.UNPROCESSABLE_ENTITY, 'negative_num_value'),
    ('hello world', 0, HTTPStatus.UNPROCESSABLE_ENTITY, 'invalid_str_count'),
    (None, None, HTTPStatus.OK, None),
]


BODY_FOR_POST_MINIONS_ENDPOINT = [
    # Positive scenarios
    ({}, HTTPStatus.OK, MinionsListModel), # Empty body
    ({'page': 1}, HTTPStatus.OK, MinionsListModel),  # Specifying the page number
    ({'per_page': 2}, HTTPStatus.OK, MinionsListModel),  # Specifying the number of records per page
    ({'query': {'grains.os': 'Ubuntu'}}, HTTPStatus.OK, MinionsListModel),  # Filter by OS
    ({'collection_id': '5eb7cf5a86d9755df3a6c593'}, HTTPStatus.OK, MinionsListModel),  # Specifying the collection
    ({'page': 1, 'per_page': 2, 'collection_id': '5eb7cf5a86d9755df3a6c593'}, HTTPStatus.OK, MinionsListModel),  # Combination of parameters
    ({'query': {'$and': [{'grains.os': 'Ubuntu'}, {'grains.mem_total': {'$gte': 8192}}]}}, HTTPStatus.OK, MinionsListModel),  # Complex filter

    # Negative scenarios
    ({'page': 'qwe'}, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),  # Incorrect type for `page`
    ({'per_page': 'qwe'}, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),  # Incorrect type for `per_page`
    ({'collection_id': 'invalid_collection_id'}, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),  # Invalid collection ID
    ({'page': -1}, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),  # Negative page number
    ({'per_page': 0}, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),  # Zero records per page
    ({'page': 1, 'per_page': 2, 'collection_id': ''}, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),  # Empty value for `collection_id`
    ({'query': {'$invalid': 'value'}}, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),  # Incorrect query parameter
]


INVALID_MID_VALUES = [
    (123, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),
    ('qwe', HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),
    ('63111a3f02fa4363a76d58a4', HTTPStatus.NOT_FOUND, NotFoundModel),
    (None, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),
    ('   ', HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),
    ('@#$', HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),
    ('1', HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),
    (True, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),
    (False, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),
]


PARAMETERS_FOR_GET_MINIONS_COLLECTION_ENDPOINT = [
    # Checking default values
    (None, None, HTTPStatus.OK, CollectionsListModel),

    # Positive tests: valid values
    (0, 20, HTTPStatus.OK, CollectionsListModel),
    (1, 50, HTTPStatus.OK, CollectionsListModel),
    (2, 100, HTTPStatus.OK, CollectionsListModel),

    # Boundary values
    (0, 1, HTTPStatus.OK, CollectionsListModel),  # Minimum valid value for per_page
    (0, 100, HTTPStatus.OK, CollectionsListModel),  # Maximum valid value in the example

    # Negative tests: values that result in errors
    (-1, 20, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),  # Invalid value for page
    (0, 0, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),  # Invalid value for per_page
    (None, -10, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),  # Negative per_page

    # Absence of optional parameters (though they are optional)
    (None, None, HTTPStatus.OK, CollectionsListModel),

    # Mixed invalid and valid parameters
    (-1, 50, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),
    (0, "abc", HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),  # Invalid type for per_page
    ("abc", 20, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),  # Invalid type for page
]


BODY_FOR_POST_MINIONS_COLLECTION_ENDPOINT = [

]
