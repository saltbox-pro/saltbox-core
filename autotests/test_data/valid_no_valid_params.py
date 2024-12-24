from datetime import timedelta, datetime
from http import HTTPStatus

from models.errors_models import ErrorResponse, ErrorTextModel
from models.jobs_models import Jobs
from models.minions_models import MinionsListModel, ListModel, CreateCollectionModel, UniqueFilterValue
from models.tasks_models import TaskTemplateBaseSchema

PARAMETERS_FOR_GET_LISTS_ENDPOINTS = [
    # Default values
    (None, None, HTTPStatus.OK, ListModel),

    # Positive tests: valid values
    # Valid page and per_page values
    (0, 20, HTTPStatus.OK, ListModel),
    (1, 50, HTTPStatus.OK, ListModel),
    (2, 100, HTTPStatus.OK, ListModel),

    # Boundary values
    # Minimum valid value for per_page
    (0, 1, HTTPStatus.OK, ListModel),

    # Maximum valid value for per_page
    (0, 100, HTTPStatus.OK, ListModel),

    # Negative tests: values that result in errors
    # Invalid value for page
    (-1, 20, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),

    # Invalid value for per_page
    (0, 0, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),

    # Negative per_page
    (None, -10, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),

    # Absence of optional parameters (though they are optional)
    (None, None, HTTPStatus.OK, ListModel),

    # Mixed invalid and valid parameters
    # Invalid page and valid per_page
    (-1, 50, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),

    # Invalid type for per_page
    (0, 'abc', HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),

    # Invalid type for page
    ('abc', 20, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),
]

# DATA DOR /jobs ENDPOINTS
VALID_AND_INVALID_PARAMS_FOR_JOBS = [
    # Valid params
    # Only start_datetime
    ((datetime.now() - timedelta(hours=4)).isoformat(), None, HTTPStatus.OK, Jobs),

    # Valid range
    ((datetime.now() - timedelta(hours=4)).isoformat(), datetime.now().isoformat(), HTTPStatus.OK, Jobs),

    # start_datetime == end_datetime
    ((datetime.now() - timedelta(hours=4)).isoformat(), (datetime.now() - timedelta(hours=4)).isoformat(),
     HTTPStatus.OK, Jobs),

    # Boundary and invalid cases
    # end_datetime < start_datetime
    ((datetime.now() - timedelta(minutes=10)).isoformat(), (datetime.now() - timedelta(minutes=2)).isoformat(),
     HTTPStatus.OK, ErrorResponse),

    # Invalid format
    # Invalid start_datetime format
    ('invalid_date', None, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),

    # Invalid end_datetime format
    (None, 'invalid_date', HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),

    # Empty start_datetime
    (' ', None, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),

    # Empty end_datetime
    (None, ' ', HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),

    # Missing params
    # Missing both params
    (None, None, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),

    # Missing start_datetime
    (None, datetime.now().isoformat(), HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),

    # Future dates
    # Future start_datetime
    ('2100-10-28T16:53:20.841870', None, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),

    # Future end_datetime
    # ((datetime.now() - timedelta(hours=4)).isoformat(), '2100-10-28T16:53:20.841870', HTTPStatus.UNPROCESSABLE_ENTITY,
    #  ErrorResponse),

    # Edge cases
    # Unix epoch as start_datetime
    ('1970-01-01T00:00:00Z', None, HTTPStatus.OK, Jobs),

    # Minimum range from epoch
    ('1970-01-01T00:00:00Z', '1970-01-01T00:01:00Z', HTTPStatus.OK, Jobs),
]

INVALID_JID = [
    # Invalid JID with large integer
    (20240999999999999999, HTTPStatus.UNPROCESSABLE_ENTITY, 'invalid_day_value'),

    # Invalid JID with small integer
    (123, HTTPStatus.UNPROCESSABLE_ENTITY, 'invalid_int_value'),

    # Invalid JID with string
    ('hello world', HTTPStatus.UNPROCESSABLE_ENTITY, 'invalid_str_value'),
]

INVALID_QUERY_PARAMS_FOR_JOB_RETURN = [
    # Negative count value
    (-1, 0, HTTPStatus.UNPROCESSABLE_ENTITY, 'negative_num_value'),

    # Invalid count type (string)
    ('hello world', 0, HTTPStatus.UNPROCESSABLE_ENTITY, 'invalid_str_count'),

    # Missing both parameters (default values)
    (None, None, HTTPStatus.OK, None),
]

# DATA FOR /filters ENDPOINTS
BODY_FOR_POST_FILTER = [
    # Positive cases
    # Valid query and field, expecting unique values for 'grains.os' matching the filter
    ({'query': {'grains.os': 'Alpine'}, 'field': 'grains.os'}, HTTPStatus.OK, UniqueFilterValue),

    # Valid field without a query, expecting all unique values for 'grains.os'
    ({'field': 'minion_id'}, HTTPStatus.OK, UniqueFilterValue),

    # Query with a non-existent field, should return an empty list of unique values
    ({'query': {'nonexistent_field': 'value'}, 'field': 'grains.os'}, HTTPStatus.OK, UniqueFilterValue),

    # Query with an empty string as a filter value, expecting valid response
    ({'query': {'grains.os': ''}, 'field': 'grains.os'}, HTTPStatus.OK, UniqueFilterValue),

    # Valid field for a different grain, expecting unique values for 'grains.cpu_model'
    ({'field': 'grains.cpu_model'}, HTTPStatus.OK, UniqueFilterValue),

    # Negative cases
    # Missing 'field' parameter, expecting an error response
    ({}, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),

    # Invalid type for 'field', expecting an error response
    ({'field': 12345}, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),

    # Query contains unsupported operator, expecting an error response
    ({'query': {'grains.os': {'$invalid_operator': 'value'}}, 'field': 'grains.os'}, HTTPStatus.UNPROCESSABLE_ENTITY,
     ErrorResponse),

    # Excessively long value for 'field', expecting an error response
    ({'field': 'a' * 1000}, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),
]

# DATA FOR /minions ENDPOINTS
BODY_FOR_POST_MINIONS_ENDPOINT = [
    # Positive scenarios
    # Empty body
    ({}, HTTPStatus.OK, MinionsListModel),

    # Specifying the page number
    ({'page': 1}, HTTPStatus.OK, MinionsListModel),

    # Specifying the number of records per page
    ({'per_page': 2}, HTTPStatus.OK, MinionsListModel),

    # Filter by OS
    ({'query': {'grains.os': 'Ubuntu'}}, HTTPStatus.OK, MinionsListModel),

    # Specifying the collection
    ({'collection_id': '5eb7cf5a86d9755df3a6c593'}, HTTPStatus.OK, MinionsListModel),

    # Combination of parameters
    ({'page': 1, 'per_page': 2, 'collection_id': '5eb7cf5a86d9755df3a6c593'}, HTTPStatus.OK, MinionsListModel),

    # Complex filter
    ({'query': {'$and': [{'grains.os': 'Ubuntu'}, {'grains.mem_total': {'$gte': 8192}}]}},
     HTTPStatus.OK, MinionsListModel),

    # Negative scenarios
    # Incorrect type for `page`
    ({'page': 'qwe'}, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),

    # Incorrect type for `per_page`
    ({'per_page': 'qwe'}, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),

    # Invalid collection ID
    ({'collection_id': 'invalid_collection_id'}, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),

    # Negative page number
    ({'page': -1}, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),

    # Zero records per page
    ({'per_page': 0}, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),

    # Empty value for `collection_id`
    ({'page': 1, 'per_page': 2, 'collection_id': ''}, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),

    # Incorrect query parameter
    ({'query': {'$invalid': 'value'}}, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorTextModel),
]

INVALID_MID_VALUES = [
    # Integer MID
    (123, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),

    # String MID
    ('qwe', HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),

    # Nonexistent MID
    ('63111a3f02fa4363a76d58a4', HTTPStatus.NOT_FOUND, ErrorTextModel),

    # None as MID
    (None, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),

    # Empty string MID
    ('   ', HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),

    # Special characters in MID
    ('@#$', HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),

    # Single digit MID
    ('1', HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),

    # Boolean True as MID
    (True, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),

    # Boolean False as MID
    (False, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),
]

# DATA FOR /collections ENDPOINTS
BODY_FOR_POST_COLLECTION_ENDPOINT = [
    # Positive scenarios
    # Valid query and title
    ({'query': {'grains.os': 'Ubuntu'}, 'title': 'Ubuntu Minions'}, HTTPStatus.OK, CreateCollectionModel),

    # Empty query
    ({'query': {}, 'title': 'All Minions'}, HTTPStatus.OK, CreateCollectionModel),

    # Missing query
    ({'title': 'Missing Query'}, HTTPStatus.OK, CreateCollectionModel),

    # Negative scenarios
    # Missing title field
    ({'query': {'grains.os': 'Ubuntu'}}, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),

    # Empty JSON in request body
    ({}, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),

    # Invalid query type
    ({'query': 'grains.os=Ubuntu', 'title': 'Invalid Query Type'}, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),

    # Invalid title type
    ({'query': {'grains.os': 'Ubuntu'}, 'title': 123}, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),
]

INVALID_CID_VALUES_FOR_COLLECTION = [
    # Nonexistent cid
    ('5eb7cf5a86d9755df3a6c999', HTTPStatus.NOT_FOUND, ErrorTextModel),

    # Empty cid
    (' ', HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),

    # Incorrect format mid
    ('12345', HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),

    # Incorrect format with special symbols
    ('5eb7cf5a86d9755!invalid', HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),

    # Incorrect format: long cid
    ('5eb7cf5a86d9755df3a6c5931234567890', HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),
]

INVALID_BODY_FOR_PUT_COLLECTION = [
    # Empty request body
    ({}, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),

    # # Body without 'query'
    # ({'title': 'Valid Title'}, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),
    #
    # # Body without 'title'
    # ({'query': {'grains.os': 'Ubuntu'}}, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),
    #
    # # Empty 'query' field
    # ({'query': {}, 'title': 'Valid Title'}, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),
    #
    # # Incorrect structure 'query' field
    # ({'query': 'Invalid Query', 'title': 'Valid Title'}, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),
    #
    # # Invalid 'query' field
    # ({'query': {'$invalid': 'value'}, 'title': 'Valid Title'}, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),
    #
    # # Empty 'title' field
    # ({'query': {'grains.os': 'Ubuntu'}, 'title': ''}, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),
    #
    # # Поле 'title' содержит слишком длинное значение
    # ({'query': {'grains.os': 'Ubuntu'}, 'title': 'a' * 256}, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),
    #
    # # Поле 'query' и 'title' пустые
    # ({'query': {}, 'title': ''}, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorResponse),
]

INVALID_CID_VALUES_FOR_DEL_COLLECTION = [
    # Nonexistent cid
    ('5eb7cf5a86d9755df3a6c999', HTTPStatus.NO_CONTENT),

    # Empty cid
    (' ', HTTPStatus.UNPROCESSABLE_ENTITY),

    # Incorrect format mid
    ('12345', HTTPStatus.UNPROCESSABLE_ENTITY),

    # Incorrect format with special symbols
    ('5eb7cf5a86d9755!invalid', HTTPStatus.UNPROCESSABLE_ENTITY),

    # Incorrect format: long cid
    ('5eb7cf5a86d9755df3a6c5931234567890', HTTPStatus.UNPROCESSABLE_ENTITY),
]

# DATA FOR /tasks
BODY_FOR_POST_TASKS_TEMPLATE_ENDPOINT = [
    # ТС001: Валидные данные
    (
        {
            'title': 'Valid Task',
            'fun': 'salt.ping',
            'variables': [
                {
                    'title': 'Timeout',
                    'name': 'timeout',
                    'type': 'number',
                    'required': True,
                    'choices': [5, 10, 15],
                    'default_value': 10,
                }
            ],
            'task_args': ['const_arg', '<<task_var.timeout>>'],
            'task_kwargs': {
                'timeout': '<<task_var.timeout>>',
            },
        },
        HTTPStatus.OK,
        TaskTemplateBaseSchema,
    ),
    # ТС002: Неверный тип данных для variables.type
    (
        {
            'title': 'Invalid Type',
            'fun': 'salt.ping',
            'variables': [
                {
                    'title': 'Timeout',
                    'name': 'timeout',
                    'type': 'int',  # Некорректный тип
                    'required': True,
                }
            ],
            'task_args': [],
            'task_kwargs': {},
        },
        HTTPStatus.UNPROCESSABLE_ENTITY,
        ErrorResponse,
    ),
    # ТС003: Пустое название задачи
    (
        {
            'title': '',
            'fun': 'salt.ping',
            'variables': [],
            'task_args': [],
            'task_kwargs': {},
        },
        HTTPStatus.UNPROCESSABLE_ENTITY,
        ErrorResponse,
    ),
    # ТС004: Пропущено обязательное поле 'fun'
    (
        {
            'title': 'Missing Fun',
            'variables': [
                {
                    'title': 'Variable',
                    'name': 'var1',
                    'type': 'str',
                    'required': True,
                }
            ],
            'task_args': [],
            'task_kwargs': {},
        },
        HTTPStatus.UNPROCESSABLE_ENTITY,
        ErrorResponse,
    ),
    # ТС005: Некорректный ключ в task_kwargs
    (
        {
            'title': 'Invalid Kwarg Key',
            'fun': 'salt.ping',
            'variables': [
                {
                    'title': 'Timeout',
                    'name': 'timeout',
                    'type': 'number',
                    'required': True,
                }
            ],
            'task_args': [],
            'task_kwargs': {
                123: '<<task_var.timeout>>',  # Ключ в виде числа, а не строки
            },
        },
        HTTPStatus.UNPROCESSABLE_ENTITY,
        ErrorResponse,
    ),
    # ТС006: Пропущено обязательное поле 'title'
    (
        {
            'fun': 'salt.ping',
            'variables': [
                {
                    'title': 'Variable',
                    'name': 'var1',
                    'type': 'str',
                    'required': True,
                }
            ],
            'task_args': ['const_arg'],
            'task_kwargs': {},
        },
        HTTPStatus.UNPROCESSABLE_ENTITY,
        ErrorResponse,
    ),
    # ТС007: Пустой список variables
    (
        {
            'title': 'Empty Variables',
            'fun': 'salt.ping',
            'variables': [],
            'task_args': ['const_arg'],
            'task_kwargs': {'key': 'value'},
        },
        HTTPStatus.OK,
        TaskTemplateBaseSchema,
    ),
]
