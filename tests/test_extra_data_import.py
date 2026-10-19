from datetime import UTC, datetime

import pytest

from saltbox_core.minion_collections.repositories.collection import CollectionRepository
from saltbox_core.minion_collections.repositories.extra_data import ExtraDataRepository
from saltbox_core.minion_collections.repositories.extra_data_category import ExtraDataCategoryRepository
from saltbox_core.minion_collections.repositories.minion import MinionRepository
from saltbox_core.minion_collections.schemas.extra_data import ExtraDataImportMode, UnknownMinionPolicy
from saltbox_core.minion_collections.schemas.extra_data_category import ExtraDataCategoryModel
from saltbox_core.minion_collections.schemas.minion import GrainsSchema, MinionCreateSchema
from saltbox_core.minion_collections.services.extra_data import ExtraDataService
from saltbox_core.minion_collections.utils.extra_data_csv import parse_csv_value, parse_import_csv
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.event_bus.schemas import MinionExtraDataCategoryFieldType as FieldType
from saltbox_sdk.exceptions import SaltBoxValidationException
from saltbox_sdk.fastapi_utils.csv_export import to_csv_value


def _category(category_type='static', fields=None, minion_fields=(), **kwargs):
    fields = fields or [{'name': 'owner'}, {'name': 'number', 'type': 'int'}]
    return ExtraDataCategoryModel.model_validate(
        {
            '_id': PyObjectId(),
            'created': datetime(2026, 9, 1, tzinfo=UTC),
            'modified': datetime(2026, 9, 1, tzinfo=UTC),
            'source': 'manual',
            'name': 'assets',
            'type': category_type,
            'is_manual_data_allowed': True,
            'fields': [{'type': 'str', **field, 'is_minion_field': field['name'] in minion_fields} for field in fields],
            **kwargs,
        }
    )


def _csv(*rows):
    return '\n'.join(','.join(row) for row in rows) + '\n'


@pytest.mark.parametrize(
    ('value', 'field_type'),
    [
        ('text', FieldType.STR),
        ('=1+2', FieldType.STR),
        ('-5', FieldType.STR),
        (42, FieldType.INT),
        (-42, FieldType.INT),
        (2.5, FieldType.FLOAT),
        (True, FieldType.BOOL),
        (False, FieldType.BOOL),
        (datetime(2026, 9, 1, 10, 30, tzinfo=UTC), FieldType.DATETIME),
        ([1, 'a'], FieldType.LIST),
        ({'a': [1, 2]}, FieldType.DICT),
    ],
)
def test_parse_csv_value_reverts_export_format(value, field_type):
    assert parse_csv_value(str(to_csv_value(value)), field_type) == value


@pytest.mark.parametrize(
    ('value', 'field_type'),
    [
        ('1.5', FieldType.INT),
        ('abc', FieldType.FLOAT),
        ('yes', FieldType.BOOL),
        ('2026-13-01', FieldType.DATETIME),
        ('{"a": 1}', FieldType.LIST),
        ('[1]', FieldType.DICT),
        ('not json', FieldType.DICT),
        ('abc', FieldType.BYTES),
    ],
)
def test_parse_csv_value_invalid(value, field_type):
    with pytest.raises(ValueError):
        parse_csv_value(value, field_type)


def test_parse_import_csv_rows():
    content = _csv(
        ['minion_id', 'master', 'owner', 'number', 'updated_at'],
        ['m1', 'salt', "'=cmd", '1', '2026-09-01T00:00:00'],
        ['', '', '', '', ''],
        ['m2', 'salt', 'Bob', '', ''],
    )

    rows, errors = parse_import_csv(_category(), content)

    assert errors == []
    assert [(row.row_number, row.minion_id, row.master, row.data) for row in rows] == [
        (2, 'm1', 'salt', {'owner': '=cmd', 'number': 1}),
        (4, 'm2', 'salt', {'owner': 'Bob'}),
    ]


def test_parse_import_csv_field_named_like_minion_columns():
    category = _category(fields=[{'name': 'master'}, {'name': 'updated_at', 'type': 'datetime'}])
    content = _csv(
        ['minion_id', 'master', 'master', 'updated_at', 'updated_at'],
        ['m1', 'salt', 'Alice', '2026-01-01T00:00:00', '2026-09-01T00:00:00'],
    )

    rows, errors = parse_import_csv(category, content)

    assert errors == []
    assert rows[0].master == 'salt'
    assert rows[0].data == {'master': 'Alice', 'updated_at': datetime(2026, 1, 1)}


def test_parse_import_csv_row_errors():
    content = _csv(
        ['minion_id', 'master', 'owner', 'number'],
        ['m1', 'salt', 'Alice', 'abc'],
        ['m2', 'salt', '', ''],
        ['m3', 'salt', 'Bob'],
    )

    rows, errors = parse_import_csv(_category(), content)

    assert rows == []
    assert errors == [
        'Row 2: `number`: expected int',
        'Row 3: extra data item must contain at least one field',
        'Row 4: expected 4 columns, got 3',
    ]


def test_parse_import_csv_validates_category_fields():
    category = _category(fields=[{'name': 'owner', 'is_empty_allowed': False}, {'name': 'number', 'type': 'int'}])
    content = _csv(['minion_id', 'master', 'number', 'color'], ['m1', 'salt', '1', 'red'])

    _rows, errors = parse_import_csv(category, content)

    assert len(errors) == 1
    assert errors[0].startswith('Row 2: Invalid extra data:')
    assert '`color`: unknown field' in errors[0]
    assert '`owner`: must not be empty' in errors[0]


@pytest.mark.parametrize(
    ('header', 'error'),
    [
        (['master', 'minion_id', 'owner'], 'The first CSV columns must be minion_id, master'),
        (['minion_id', 'master', 'owner', 'owner'], '`owner`: duplicated column'),
        (['minion_id', 'master', 'blob'], '`blob`: bytes fields are not supported in CSV'),
    ],
)
def test_parse_import_csv_header_errors(header, error):
    category = _category(fields=[{'name': 'owner'}, {'name': 'blob', 'type': 'bytes'}])

    with pytest.raises(SaltBoxValidationException, match=error):
        parse_import_csv(category, _csv(header))


def test_parse_import_csv_empty_file():
    with pytest.raises(SaltBoxValidationException, match='empty'):
        parse_import_csv(_category(), '')


# Service


@pytest.fixture
def service(mocked_db):
    category_repo = ExtraDataCategoryRepository(mocked_db)
    extra_data_repo = ExtraDataRepository(mocked_db, extra_data_category_repository=category_repo)
    minion_repo = MinionRepository(
        mocked_db, extra_data_repository=extra_data_repo, collection_repository=CollectionRepository(mocked_db)
    )

    return ExtraDataService(extra_data_repo, minion_repo=minion_repo)


@pytest.fixture
def create_minion(service):
    async def create(minion_id, master='salt', os='ALT'):
        return await service.minion_repo.create(
            MinionCreateSchema(minion_id=minion_id, master=master, grains=GrainsSchema(os=os))
        )

    return create


async def _import(service, category, content, mode=ExtraDataImportMode.APPEND, **kwargs):
    return await service.import_items(
        category,
        content,
        query=kwargs.pop('query', {'grains.os': 'ALT'}),
        mode=mode,
        on_unknown_minion=kwargs.pop('on_unknown_minion', UnknownMinionPolicy.ERROR),
    )


async def _static_items(service, minion_id):
    minion = await service.minion_repo.collection.find_one({'_id': minion_id})
    return [item['data'] for item in minion.get('extra_static', {}).get('manual', {}).get('assets', [])]


@pytest.mark.asyncio
async def test_import_static_items_appends(service, create_minion):
    first_id = await create_minion('m1')
    second_id = await create_minion('m2')
    category = _category()
    await service.add_items(category, [first_id], {'owner': 'Old'}, is_system=False)

    result = await _import(
        service,
        category,
        _csv(
            ['minion_id', 'master', 'owner', 'number'],
            ['m1', 'salt', 'Alice', '1'],
            ['m2', 'salt', 'Bob', '2'],
            ['m1', 'salt', 'Carol', ''],
        ),
    )

    assert result.model_dump() == {'minions_count': 2, 'items_count': 3, 'skipped_rows': []}
    assert await _static_items(service, first_id) == [
        {'owner': 'Old'},
        {'owner': 'Alice', 'number': 1},
        {'owner': 'Carol'},
    ]
    assert await _static_items(service, second_id) == [{'owner': 'Bob', 'number': 2}]


@pytest.mark.asyncio
async def test_import_aggregated_items_groups_category_data(service, create_minion, mocked_db):
    await create_minion('m1')
    await create_minion('m2')
    category = _category('aggregated', minion_fields=('number',))

    result = await _import(
        service,
        category,
        _csv(['minion_id', 'master', 'owner', 'number'], ['m1', 'salt', 'Alice', '1'], ['m2', 'salt', 'Alice', '2']),
    )

    records = list(mocked_db['minion_extra_data'].collection.find({'source': 'manual', 'name': 'assets'}))
    assert result.items_count == 2
    assert len(records) == 1
    assert records[0]['data'] == {'owner': 'Alice'}
    assert sorted(entry['data']['number'] for entry in records[0]['minions']) == [1, 2]


@pytest.mark.asyncio
async def test_import_unknown_and_outside_minions(service, create_minion):
    await create_minion('m1')
    await create_minion('m2', os='Ubuntu')
    content = _csv(
        ['minion_id', 'master', 'owner'],
        ['m1', 'salt', 'Alice'],
        ['m1', 'other-master', 'Bob'],
        ['m2', 'salt', 'Carol'],
        ['missing', 'salt', 'Dave'],
    )
    category = _category(fields=[{'name': 'owner'}])

    with pytest.raises(SaltBoxValidationException) as exc_info:
        await _import(service, category, content)

    assert 'Row 3: minion `m1` with master `other-master` not found' in exc_info.value.detail
    assert 'Row 4: minion `m2` with master `salt` is not in the collection' in exc_info.value.detail
    assert 'Row 5: minion `missing` with master `salt` not found' in exc_info.value.detail

    result = await _import(service, category, content, on_unknown_minion=UnknownMinionPolicy.SKIP)

    assert result.model_dump() == {'minions_count': 1, 'items_count': 1, 'skipped_rows': [3, 4, 5]}


@pytest.mark.asyncio
async def test_import_writes_nothing_on_errors(service, create_minion):
    minion_id = await create_minion('m1')

    with pytest.raises(SaltBoxValidationException, match='Row 3'):
        await _import(
            service,
            _category(),
            _csv(['minion_id', 'master', 'owner', 'number'], ['m1', 'salt', 'Alice', '1'], ['m1', 'salt', 'Bob', 'x']),
        )

    assert await _static_items(service, minion_id) == []


@pytest.mark.asyncio
async def test_import_single_item_category_rejects_several_rows_per_minion(service, create_minion):
    await create_minion('m1')

    with pytest.raises(SaltBoxValidationException, match='Rows 2, 3: category allows only one item per minion'):
        await _import(
            service,
            _category(is_single_item=True),
            _csv(['minion_id', 'master', 'owner'], ['m1', 'salt', 'Alice'], ['m1', 'salt', 'Bob']),
        )
