from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import mongomock
import pytest

from saltbox_core.minion_collections.repositories.extra_data import ExtraDataRepository
from saltbox_core.minion_collections.repositories.minion import MinionRepository
from saltbox_core.minion_collections.schemas.extra_data_category import ExtraDataCategoryModel
from saltbox_core.minion_collections.schemas.filter import ExtraFilterValuesBody, MinionFilterValuesBody
from saltbox_core.minion_collections.services.extra_data import ExtraDataService
from saltbox_core.minion_collections.services.minion import MinionService
from saltbox_core.minion_collections.utils.unique_values import UniqueValueKind
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.exceptions import SaltBoxValidationException

MINION_1 = PyObjectId()
MINION_2 = PyObjectId()
MINION_3 = PyObjectId()


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    async def to_list(self):
        return self.docs


class _Collection:
    def __init__(self, docs):
        self.collection = mongomock.MongoClient().db.collection
        self.collection.insert_many(docs)

    async def aggregate(self, pipeline, session=None, **kwargs):
        return _Cursor(list(self.collection.aggregate(pipeline)))


def _values(data):
    return {item['value']: item['count'] for item in data}


async def _grain_values(grain, kind, skip=0, limit=0):
    docs = [
        {
            '_id': MINION_1,
            'grains': {
                'os': 'ALT',
                'ipv4': ['10.0.0.1', '10.0.0.1', '127.0.0.1'],
                'hwaddr_interfaces': {'eth0': 'aa', 'lo': '00'},
            },
        },
        {'_id': MINION_2, 'grains': {'os': 'ALT', 'ipv4': ['127.0.0.1'], 'hwaddr_interfaces': {'lo': '00'}}},
        {'_id': MINION_3, 'grains': {'os': 'Ubuntu'}},
    ]
    repository = MinionRepository.__new__(MinionRepository)

    with patch.object(MinionRepository, 'collection', _Collection(docs)):
        return await repository.get_unique_grain_values({}, grain, kind, skip, limit)


@pytest.mark.asyncio
async def test_grain_values_are_counted_per_minion_and_sorted():
    total, data = await _grain_values('os', UniqueValueKind.VALUE)

    assert total == 2
    assert data == [{'value': 'ALT', 'count': 2}, {'value': 'Ubuntu', 'count': 1}]


@pytest.mark.asyncio
async def test_grain_list_items_count_each_minion_once():
    total, data = await _grain_values('ipv4', UniqueValueKind.LIST_ITEMS)

    assert total == 2
    assert _values(data) == {'127.0.0.1': 2, '10.0.0.1': 1}


@pytest.mark.asyncio
async def test_grain_dict_keys():
    _, data = await _grain_values('hwaddr_interfaces', UniqueValueKind.DICT_KEYS)

    assert _values(data) == {'lo': 2, 'eth0': 1}


@pytest.mark.asyncio
async def test_grain_values_page_keeps_full_total():
    total, data = await _grain_values('os', UniqueValueKind.VALUE, skip=1, limit=1)

    assert total == 2
    assert data == [{'value': 'Ubuntu', 'count': 1}]


@pytest.mark.parametrize(
    ('grain', 'kind'),
    [
        ('os', UniqueValueKind.VALUE),
        ('ip6_gw', UniqueValueKind.VALUE),
        ('ipv4', UniqueValueKind.LIST_ITEMS),
        ('gpus', UniqueValueKind.LIST_ITEMS),
        ('hwaddr_interfaces', UniqueValueKind.DICT_KEYS),
        ('ip4_interfaces', UniqueValueKind.DICT_KEYS),
        ('saltversioninfo', UniqueValueKind.JOINED_LIST),
        ('efi-secure-boot', UniqueValueKind.VALUE),
        ('custom_grain', UniqueValueKind.VALUE),
    ],
)
@pytest.mark.asyncio
async def test_grain_kind_is_detected_by_schema(grain, kind):
    repository = AsyncMock()
    repository.__prepare_query__ = AsyncMock(return_value={})
    repository.get_unique_grain_values.return_value = (0, [])

    await MinionService(repository).get_unique_grain_values(f'grains.{grain}', {})

    assert repository.get_unique_grain_values.call_args.kwargs['kind'] == kind
    assert repository.get_unique_grain_values.call_args.kwargs['grain'] == grain


@pytest.mark.asyncio
async def test_not_grain_field_returns_empty():
    repository = AsyncMock()

    result = await MinionService(repository).get_unique_grain_values('minion_id', {})

    assert result.total == 0
    assert result.data == []
    repository.get_unique_grain_values.assert_not_called()


@pytest.mark.parametrize('field', ['grains.', 'grains..os', 'grains.$os', '$grains'])
def test_malformed_grain_field_is_rejected(field):
    with pytest.raises(SaltBoxValidationException):
        MinionFilterValuesBody(field=field)


def _category(category_type):
    return ExtraDataCategoryModel(
        _id=PyObjectId(),
        created=datetime(2026, 10, 1, tzinfo=UTC),
        modified=datetime(2026, 10, 1, tzinfo=UTC),
        source='manual',
        name='monitors',
        type=category_type,
        fields=[
            {'name': 'room', 'type': 'str'},
            {'name': 'tags', 'type': 'list'},
            {'name': 'bought', 'type': 'datetime'},
            {'name': 'specs', 'type': 'dict'},
            {'name': 'serial', 'type': 'str', 'is_minion_field': True},
        ],
    )


def _static_item(data):
    return {'_id': PyObjectId(), 'is_system': False, 'data': data}


async def _static_values(field_name):
    docs = [
        {
            '_id': MINION_1,
            'extra_static': {
                'manual': {
                    'monitors': [
                        _static_item({'room': '101', 'tags': ['a', 'b'], 'bought': datetime(2026, 1, 2, 10)}),
                        _static_item({'room': '101', 'tags': ['a'], 'bought': datetime(2026, 1, 2, 18)}),
                    ]
                }
            },
        },
        {'_id': MINION_2, 'extra_static': {'manual': {'monitors': [_static_item({'room': '102', 'tags': ['a']})]}}},
        {'_id': MINION_3},
    ]
    minion_repo = MinionRepository.__new__(MinionRepository)
    minion_repo.__prepare_query__ = AsyncMock(return_value={})
    service = ExtraDataService(AsyncMock(), minion_repo=minion_repo)

    with patch.object(MinionRepository, 'collection', _Collection(docs)):
        return await service.get_unique_values(_category('static'), field_name, query={})


@pytest.mark.asyncio
async def test_static_values_count_each_minion_once():
    result = await _static_values('room')

    assert result.total == 2
    assert [item.model_dump() for item in result.data] == [
        {'value': '101', 'count': 1},
        {'value': '102', 'count': 1},
    ]


@pytest.mark.asyncio
async def test_static_list_values():
    result = await _static_values('tags')

    assert {item.value: item.count for item in result.data} == {'a': 2, 'b': 1}


@pytest.mark.asyncio
async def test_static_datetime_values_are_grouped_by_day():
    result = await _static_values('bought')

    assert {item.value: item.count for item in result.data} == {'2026-01-02': 1, None: 1}


@pytest.mark.parametrize('field_name', ['specs', 'unknown'])
@pytest.mark.asyncio
async def test_unsupported_extra_field_returns_empty(field_name):
    minion_repo = AsyncMock()
    service = ExtraDataService(AsyncMock(), minion_repo=minion_repo)

    result = await service.get_unique_values(_category('static'), field_name, query={})

    assert result.total == 0
    assert result.data == []
    minion_repo.get_unique_static_extra_values.assert_not_called()


def _entry(minion_id, data):
    return {'_id': PyObjectId(), 'minion_id': minion_id, 'is_system': False, 'data': data}


async def _aggregated_values(field_name, minion_ids):
    docs = [
        {
            'source': 'manual',
            'name': 'monitors',
            'data': {'room': '101'},
            'minions': [
                _entry(MINION_1, {'serial': 'SN1'}),
                _entry(MINION_1, {'serial': 'SN2'}),
                _entry(MINION_2, {'serial': 'SN1'}),
            ],
        },
        {'source': 'manual', 'name': 'monitors', 'data': {'room': '102'}, 'minions': [_entry(MINION_3, {})]},
        {'source': 'manual', 'name': 'other', 'data': {'room': '103'}, 'minions': [_entry(MINION_1, {})]},
    ]
    minion_repo = AsyncMock()
    minion_repo.__prepare_query__ = AsyncMock(return_value={})
    minion_repo.get_ids.return_value = minion_ids
    repository = ExtraDataRepository.__new__(ExtraDataRepository)
    service = ExtraDataService(repository, minion_repo=minion_repo)

    with patch.object(ExtraDataRepository, 'collection', _Collection(docs)):
        return await service.get_unique_values(_category('aggregated'), field_name, query={})


@pytest.mark.asyncio
async def test_aggregated_category_field_values():
    result = await _aggregated_values('room', [MINION_1, MINION_2, MINION_3])

    assert {item.value: item.count for item in result.data} == {'101': 2, '102': 1}


@pytest.mark.asyncio
async def test_aggregated_minion_field_values_are_limited_by_minions():
    result = await _aggregated_values('serial', [MINION_1, MINION_3])

    assert {item.value: item.count for item in result.data} == {'SN1': 1, 'SN2': 1, None: 1}


@pytest.mark.parametrize(
    'data',
    [
        {'field': 'room'},
        {'field': 'room', 'category_source': 'manual'},
        {'field': 'room', 'category_id': str(PyObjectId()), 'category_source': 'manual', 'category_name': 'x'},
    ],
)
def test_extra_body_requires_single_category_ref(data):
    with pytest.raises(SaltBoxValidationException):
        ExtraFilterValuesBody(**data)


@pytest.mark.parametrize(
    'data',
    [
        {'field': 'room', 'category_id': str(PyObjectId())},
        {'field': 'room', 'category_source': 'manual', 'category_name': 'monitors'},
    ],
)
def test_extra_body_accepts_category_ref(data):
    assert ExtraFilterValuesBody(**data).field == 'room'
