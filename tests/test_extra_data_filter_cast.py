from datetime import UTC, datetime

import pytest

from saltbox_core.minion_collections.schemas.extra_data_category import ExtraDataCategoryModel
from saltbox_sdk.db.mongo.schemas_base import PyObjectId


def _category():
    return ExtraDataCategoryModel(
        _id=PyObjectId(),
        created=datetime(2026, 9, 1, tzinfo=UTC),
        modified=datetime(2026, 9, 1, tzinfo=UTC),
        source='manual',
        name='assets',
        type='static',
        fields=[
            {'name': 'owner', 'type': 'str'},
            {'name': 'number', 'type': 'int'},
            {'name': 'weight', 'type': 'float'},
            {'name': 'is_laptop', 'type': 'bool'},
            {'name': 'bought_at', 'type': 'datetime'},
        ],
    )


@pytest.mark.parametrize(
    ('field_name', 'value', 'expected'),
    [
        ('number', '1336', 1336),
        ('number', 1336, 1336),
        ('number', 'abc', 'abc'),
        ('number', '13.5', '13.5'),
        ('number', None, None),
        ('weight', '2.5', 2.5),
        ('weight', '2', 2.0),
        ('owner', 1336, '1336'),
        ('owner', 13.5, '13.5'),
        ('owner', True, True),
        ('owner', 'Иванова', 'Иванова'),
        ('is_laptop', 'true', 'true'),
        ('bought_at', '2026-09-01T10:00:00+00:00', datetime(2026, 9, 1, 10, tzinfo=UTC)),
        ('unknown', '1336', '1336'),
        ('number.sub', '1336', '1336'),
    ],
)
def test_plain_value_is_cast(field_name, value, expected):
    assert _category().cast_filter_value(field_name=field_name, value=value) == expected


@pytest.mark.parametrize(
    ('field_name', 'value', 'expected'),
    [
        ('number', {'$eq': '1336'}, {'$eq': 1336}),
        ('number', {'$ne': '1336'}, {'$ne': 1336}),
        ('number', {'$in': ['1336', '1337', 1338]}, {'$in': [1336, 1337, 1338]}),
        ('owner', {'$nin': [1336, 'x']}, {'$nin': ['1336', 'x']}),
        ('number', {'$gt': '10', '$lte': '20'}, {'$gt': 10, '$lte': 20}),
        ('owner', {'$lt': 10}, {'$lt': '10'}),
        ('number', {'$gt': 'abc'}, {'$gt': 'abc'}),
        ('number', {'$exists': True}, {'$exists': True}),
        ('owner', {'$regex': '^Ив'}, {'$regex': '^Ив'}),
    ],
)
def test_lookup_value_is_cast(field_name, value, expected):
    assert _category().cast_filter_value(field_name=field_name, value=value) == expected
