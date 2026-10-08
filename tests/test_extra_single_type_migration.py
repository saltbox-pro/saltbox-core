import importlib
from datetime import UTC, datetime

import pytest

migration = importlib.import_module('saltbox_core.minion_collections.migrations.0004_single_type_extra_fields')


def _stats():
    return {'cast_values': 0, 'dropped_values': 0, 'dropped_items': 0}


@pytest.mark.parametrize(
    ('types', 'expected'),
    [
        (['int'], 'int'),
        (['int', 'none'], 'int'),
        (['datetime'], 'datetime'),
        (['str', 'int', 'none'], 'str'),
        (['int', 'str'], 'str'),
        (['int', 'float'], 'float'),
        (['bool', 'int'], 'str'),
        (['none'], 'str'),
        ([], 'str'),
    ],
)
def test_single_type(types, expected):
    assert migration.get_single_type(types) == expected


def test_inventory_category_fields_come_from_snapshot():
    category = {
        'source': 'inventory',
        'name': 'monitors',
        'fields': [{'name': 'serial_number', 'types': []}],
        'minion_fields': [],
    }

    fields = {field['name']: field for field in migration.get_category_fields(category)}

    assert fields['serial_number'] == {
        'name': 'serial_number',
        'type': 'str',
        'is_empty_allowed': True,
        'is_minion_field': True,
    }
    assert fields['diagonal']['type'] == 'float'
    assert fields['diagonal']['is_minion_field'] is False


def test_manual_category_fields_come_from_stored_types():
    category = {
        'source': 'manual',
        'name': 'assets',
        'fields': [{'name': 'code', 'types': ['str', 'int']}, {'name': 'seat', 'types': ['int', 'none']}],
        'minion_fields': ['seat'],
    }

    assert migration.get_category_fields(category) == [
        {'name': 'code', 'type': 'str', 'is_empty_allowed': True, 'is_minion_field': False},
        {'name': 'seat', 'type': 'int', 'is_empty_allowed': True, 'is_minion_field': True},
    ]


def test_already_migrated_manual_fields_are_kept():
    field = {'name': 'code', 'type': 'str', 'is_empty_allowed': False, 'is_minion_field': True}

    assert migration.get_category_fields({'source': 'manual', 'name': 'assets', 'fields': [field]}) == [field]


def test_cast_data_casts_to_field_types():
    stats = _stats()
    data = {
        'serial': 46502,
        'cores': '8',
        'diagonal': '23.8',
        'weight': 2,
        'seen_at': '2026-09-01T00:00:00+00:00',
        'name': 'P2419H',
        'empty': None,
        'blank': '',
        'unknown': 1,
    }
    field_types = {
        'serial': 'str',
        'cores': 'int',
        'diagonal': 'float',
        'weight': 'float',
        'seen_at': 'datetime',
        'name': 'str',
        'empty': 'int',
        'blank': 'int',
    }

    assert migration.cast_data(data, field_types, stats) == {
        'serial': '46502',
        'cores': 8,
        'diagonal': 23.8,
        'weight': 2,
        'seen_at': datetime(2026, 9, 1, tzinfo=UTC),
        'name': 'P2419H',
        'empty': None,
        'blank': '',
        'unknown': 1,
    }
    assert stats == {'cast_values': 4, 'dropped_values': 0, 'dropped_items': 0}


@pytest.mark.parametrize(
    ('value', 'field_type'),
    [
        (True, 'str'),
        ([1, 2], 'str'),
        ({'a': 1}, 'str'),
        ('abc', 'int'),
        ('2.5', 'int'),
        (2.5, 'int'),
        (True, 'int'),
        ('yesterday', 'datetime'),
        (1, 'bool'),
    ],
)
def test_cast_data_drops_values_that_cannot_be_cast(value, field_type):
    stats = _stats()

    assert migration.cast_data({'field': value, 'model': 'x'}, {'field': field_type}, stats) == {'model': 'x'}
    assert stats['dropped_values'] == 1


def test_cast_items_drops_only_items_emptied_by_casting():
    stats = _stats()
    items = [{'data': {'cores': 'abc'}}, {'data': {}}, {'data': {'cores': '4'}}]

    assert migration.cast_items(items, {'cores': 'int'}, stats) == [{'data': {}}, {'data': {'cores': 4}}]
    assert stats['dropped_items'] == 1
