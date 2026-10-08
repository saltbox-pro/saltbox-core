from datetime import UTC, datetime

import pytest

from saltbox_core.minion_collections.schemas.extra_data_category import ExtraDataCategoryModel
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.exceptions import SaltBoxValidationException


def _category(extra_fields_policy='ignore', fields=None):
    return ExtraDataCategoryModel(
        _id=PyObjectId(),
        created=datetime(2026, 9, 1, tzinfo=UTC),
        modified=datetime(2026, 9, 1, tzinfo=UTC),
        source='manual',
        name='assets',
        type='static',
        extra_fields_policy=extra_fields_policy,
        fields=fields
        or [
            {'name': 'owner', 'type': 'str'},
            {'name': 'cores', 'type': 'int'},
            {'name': 'weight', 'type': 'float'},
            {'name': 'is_laptop', 'type': 'bool'},
            {'name': 'bought_at', 'type': 'datetime'},
            {'name': 'tags', 'type': 'list'},
        ],
    )


def _required_category():
    return _category(
        fields=[
            {'name': 'model', 'type': 'str', 'is_empty_allowed': False},
            {'name': 'serial', 'type': 'str', 'is_empty_allowed': False, 'is_minion_field': True},
            {'name': 'room', 'type': 'str', 'is_minion_field': True},
        ]
    )


def test_valid_data_is_cleaned():
    data = {
        'owner': 'Иванова',
        'cores': None,
        'weight': 2,
        'is_laptop': True,
        'bought_at': '2026-09-01T10:00:00Z',
        'tags': [1, 'two'],
    }

    cleaned = _category().clean_data(data)

    assert cleaned == {**data, 'bought_at': datetime(2026, 9, 1, 10, tzinfo=UTC)}


@pytest.mark.parametrize(
    ('data', 'error'),
    [
        ({'owner': 42}, '`owner`: expected str'),
        ({'cores': True}, '`cores`: expected int'),
        ({'cores': 2.5}, '`cores`: expected int'),
        ({'weight': False}, '`weight`: expected float'),
        ({'bought_at': 'вчера'}, '`bought_at`: expected datetime'),
        ({'tags': 'one'}, '`tags`: expected list'),
        ({'room': '204'}, '`room`: unknown field'),
    ],
)
def test_invalid_data_is_rejected(data, error):
    with pytest.raises(SaltBoxValidationException, match=error):
        _category().clean_data(data)


def test_all_errors_are_reported_together():
    with pytest.raises(SaltBoxValidationException) as exc_info:
        _category().clean_data({'owner': 1, 'room': '204'})

    assert '`owner`' in exc_info.value.detail
    assert '`room`' in exc_info.value.detail


@pytest.mark.parametrize('extra_fields_policy', ['save_to_category', 'save_to_minion'])
def test_unknown_fields_are_kept_when_policy_saves_them(extra_fields_policy):
    cleaned = _category(extra_fields_policy).clean_data({'room': '204'})

    assert cleaned == {'room': '204'}


@pytest.mark.parametrize('room', [None, ''])
def test_empty_allowed_fields_may_be_empty(room):
    cleaned = _required_category().clean_data({'model': 'P2419H', 'serial': 'SN1', 'room': room})

    assert cleaned == {'model': 'P2419H', 'serial': 'SN1', 'room': room}


@pytest.mark.parametrize(
    'data',
    [
        {'serial': 'SN1'},
        {'model': None, 'serial': 'SN1'},
        {'model': '', 'serial': 'SN1'},
    ],
)
def test_required_field_empty_is_rejected(data):
    with pytest.raises(SaltBoxValidationException, match='`model`: must not be empty'):
        _required_category().clean_data(data)


def test_minion_data_only_requires_only_minion_fields():
    category = _required_category()

    assert category.clean_data({'serial': 'SN1'}, is_minion_data_only=True) == {'serial': 'SN1'}

    with pytest.raises(SaltBoxValidationException, match='`serial`: must not be empty'):
        category.clean_data({'room': '204'}, is_minion_data_only=True)


def test_split_data_uses_minion_field_flag():
    category = _required_category()

    assert category.category_fields == ['model']
    assert category.minion_fields == ['serial', 'room']
    assert category.split_data({'serial': 'SN1', 'model': 'P2419H', 'room': '204'}) == (
        {'model': 'P2419H'},
        {'serial': 'SN1', 'room': '204'},
    )
