from datetime import timedelta, datetime
from http import HTTPStatus

from models.errors_models import ErrorResponse, NotFoundModel
from models.jobs_models import Jobs
from models.minions_models import MinionsListModel

VALID_AND_INVALID_PARAMS = [
    # Valid params
    ((datetime.now() - timedelta(hours=4)).isoformat(), None, HTTPStatus.OK, Jobs),
    ((datetime.now() - timedelta(hours=4)).isoformat(), datetime.now().isoformat(), HTTPStatus.OK, Jobs),
    # No Valid params
    (None, None, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),
    (None, datetime.now().isoformat(), HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),
    ('2100-10-28T16:53:20.841870', None, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),
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


PARAMETERS_FOR_MINIONS_ENDPOINT = [
    (None, None, None, HTTPStatus.OK, MinionsListModel),
    (None, 1, None, HTTPStatus.OK, MinionsListModel),
    (2, None, None, HTTPStatus.OK, MinionsListModel),
    (2, 1, None, HTTPStatus.OK, MinionsListModel),
    (2, 1, '{ "master": "salt-master"}', HTTPStatus.OK, MinionsListModel),
    ('qwe', None, None, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),
    (None, 'qwe', None, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),
    (None, None, 'qwe', HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),
]


INVALID_MID_VALUES = [
    (123, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),
    ('qwe', HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),
    ('63111a3f02fa4363a76d58a4', HTTPStatus.NOT_FOUND, NotFoundModel),
    (None, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),
]
