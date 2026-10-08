from datetime import UTC, datetime

import pytest

from saltbox_core.minion_collections.repositories.extra_data import ExtraDataRepository
from saltbox_core.minion_collections.repositories.extra_data_category import ExtraDataCategoryRepository
from saltbox_core.minion_collections.repositories.minion import MinionRepository
from saltbox_core.minion_collections.schemas.extra_data_category import ExtraDataCategoryModel
from saltbox_core.minion_collections.schemas.minion import GrainsSchema, MinionCreateSchema
from saltbox_core.minion_collections.services.extra_data import ExtraDataService
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.exceptions import ObjectNotFoundException, PermissionDeniedException, SaltBoxValidationException


def _build_service(mocked_db):
    category_repo = ExtraDataCategoryRepository(mocked_db)
    extra_data_repo = ExtraDataRepository(mocked_db, extra_data_category_repository=category_repo)
    minion_repo = MinionRepository(mocked_db, extra_data_repository=extra_data_repo)

    return ExtraDataService(extra_data_repo, minion_repo=minion_repo), minion_repo


def _category(category_type='static', fields=None, minion_fields=(), **kwargs):
    fields = fields or [{'name': 'text'}, {'name': 'serial'}]
    data = {
        '_id': PyObjectId(),
        'created': datetime(2026, 9, 1, tzinfo=UTC),
        'modified': datetime(2026, 9, 1, tzinfo=UTC),
        'source': 'manual',
        'name': 'notes',
        'type': category_type,
        'fields': [{'type': 'str', **field, 'is_minion_field': field['name'] in minion_fields} for field in fields],
        **kwargs,
    }
    return ExtraDataCategoryModel.model_validate(data)


async def _create_minion(minion_repo, minion_id='m1'):
    return await minion_repo.create(MinionCreateSchema(minion_id=minion_id, master='master1', grains=GrainsSchema()))


# STATIC


@pytest.mark.asyncio
async def test_add_static_items(mocked_db):
    extra_data_service, minion_repo = _build_service(mocked_db)
    first_minion_id = await _create_minion(minion_repo)
    second_minion_id = await _create_minion(minion_repo, 'm2')

    items = await extra_data_service.add_items(
        _category(), [first_minion_id, second_minion_id, PyObjectId()], {'text': 'hello'}, is_system=False
    )

    assert [item['minion_id'] for item in items] == [first_minion_id, second_minion_id]
    assert items[0]['_id'] != items[1]['_id']

    for item in items:
        assert item['is_system'] is False
        stored = await minion_repo.get_static_extra_data_item(item['minion_id'], 'manual', 'notes', item['_id'])
        assert stored['data'] == {'text': 'hello'}


@pytest.mark.asyncio
async def test_add_items_to_missing_minions(mocked_db):
    extra_data_service, _minion_repo = _build_service(mocked_db)

    assert await extra_data_service.add_items(_category(), [PyObjectId()], {'text': 'hello'}, is_system=False) == []


@pytest.mark.asyncio
async def test_delete_manual_static_item(mocked_db):
    extra_data_service, minion_repo = _build_service(mocked_db)
    minion_id = await _create_minion(minion_repo)
    category = _category()

    items = await extra_data_service.add_items(category, [minion_id], {'text': 'hello'}, is_system=False)
    await extra_data_service.delete_item(category, minion_id, items[0]['_id'])

    assert await minion_repo.get_static_extra_data_item(minion_id, 'manual', 'notes', items[0]['_id']) is None


@pytest.mark.asyncio
async def test_cannot_delete_system_static_item(mocked_db):
    extra_data_service, minion_repo = _build_service(mocked_db)
    minion_id = await _create_minion(minion_repo)
    category = _category()

    items = await extra_data_service.add_items(category, [minion_id], {'text': 'hello'}, is_system=True)

    with pytest.raises(PermissionDeniedException):
        await extra_data_service.delete_item(category, minion_id, items[0]['_id'])

    assert await minion_repo.get_static_extra_data_item(minion_id, 'manual', 'notes', items[0]['_id'])


@pytest.mark.asyncio
async def test_delete_missing_static_item_raises_not_found(mocked_db):
    extra_data_service, minion_repo = _build_service(mocked_db)
    minion_id = await _create_minion(minion_repo)

    with pytest.raises(ObjectNotFoundException):
        await extra_data_service.delete_item(_category(), minion_id, PyObjectId())


# AGGREGATED


@pytest.mark.asyncio
async def test_add_aggregated_items(mocked_db):
    extra_data_service, minion_repo = _build_service(mocked_db)
    first_minion_id = await _create_minion(minion_repo)
    second_minion_id = await _create_minion(minion_repo, 'm2')
    category = _category('aggregated', minion_fields=['serial'])

    items = await extra_data_service.add_items(
        category, [first_minion_id, second_minion_id], {'serial': 'S-1', 'text': 'Office'}, is_system=False
    )

    assert [item['data'] for item in items] == [{'text': 'Office', 'serial': 'S-1'}] * 2
    record = await extra_data_service.repo.collection.find_one({'source': 'manual', 'name': 'notes'})
    assert record['data'] == {'text': 'Office'}
    assert [entry['minion_id'] for entry in record['minions']] == [first_minion_id, second_minion_id]
    assert [entry['_id'] for entry in record['minions']] == [item['_id'] for item in items]
    assert all(entry['data'] == {'serial': 'S-1'} and entry['is_system'] is False for entry in record['minions'])


@pytest.mark.asyncio
async def test_add_aggregated_items_to_existing_record(mocked_db):
    extra_data_service, minion_repo = _build_service(mocked_db)
    first_minion_id = await _create_minion(minion_repo)
    second_minion_id = await _create_minion(minion_repo, 'm2')
    category = _category('aggregated', minion_fields=['serial'])

    await extra_data_service.add_items(category, [first_minion_id], {'text': 'Office', 'serial': '1'}, is_system=False)
    await extra_data_service.add_items(category, [second_minion_id], {'serial': '2', 'text': 'Office'}, is_system=False)

    records = await extra_data_service.repo.collection.find({'source': 'manual', 'name': 'notes'}).to_list()
    assert len(records) == 1
    assert [entry['data'] for entry in records[0]['minions']] == [{'serial': '1'}, {'serial': '2'}]


@pytest.mark.asyncio
async def test_delete_manual_aggregated_item_keeps_record(mocked_db):
    extra_data_service, minion_repo = _build_service(mocked_db)
    minion_id = await _create_minion(minion_repo)
    category = _category('aggregated')

    items = await extra_data_service.add_items(category, [minion_id], {'text': 'Office'}, is_system=False)
    await extra_data_service.delete_item(category, minion_id, items[0]['_id'])

    record = await extra_data_service.repo.collection.find_one({'source': 'manual', 'name': 'notes'})
    assert record['minions'] == []


@pytest.mark.asyncio
async def test_update_aggregated_item_rejects_category_fields(mocked_db):
    extra_data_service, minion_repo = _build_service(mocked_db)
    minion_id = await _create_minion(minion_repo)

    with pytest.raises(SaltBoxValidationException):
        await extra_data_service.update_item(
            _category('aggregated', minion_fields=['serial']), minion_id, PyObjectId(), {'text': 'Office'}
        )


def test_split_data_sorts_category_data_keys():
    category = _category(
        'aggregated', fields=[{'name': 'b'}, {'name': 'a'}, {'name': 'serial'}], minion_fields=['serial']
    )

    category_data, minion_data = category.split_data({'serial': 'S-1', 'b': 2, 'a': 1})

    assert list(category_data) == ['a', 'b']
    assert minion_data == {'serial': 'S-1'}


# Rules


@pytest.mark.asyncio
@pytest.mark.parametrize('category_type', ['static', 'aggregated'])
async def test_add_empty_data_is_rejected(mocked_db, category_type):
    extra_data_service, minion_repo = _build_service(mocked_db)
    minion_id = await _create_minion(minion_repo)

    with pytest.raises(SaltBoxValidationException):
        await extra_data_service.add_items(_category(category_type), [minion_id], {}, is_system=False)


@pytest.mark.asyncio
async def test_add_invalid_data_is_rejected(mocked_db):
    extra_data_service, minion_repo = _build_service(mocked_db)
    minion_id = await _create_minion(minion_repo)

    with pytest.raises(SaltBoxValidationException):
        await extra_data_service.add_items(_category(), [minion_id], {'text': 1}, is_system=False)


@pytest.mark.asyncio
async def test_update_with_empty_data_is_rejected(mocked_db):
    extra_data_service, minion_repo = _build_service(mocked_db)
    minion_id = await _create_minion(minion_repo)
    category = _category()
    items = await extra_data_service.add_items(category, [minion_id], {'text': 'hello'}, is_system=False)

    with pytest.raises(SaltBoxValidationException):
        await extra_data_service.update_item(category, minion_id, items[0]['_id'], {})

    stored = await minion_repo.get_static_extra_data_item(minion_id, 'manual', 'notes', items[0]['_id'])
    assert stored['data'] == {'text': 'hello'}


@pytest.mark.asyncio
async def test_single_item_category_add_replaces(mocked_db, mocker):
    extra_data_service, minion_repo = _build_service(mocked_db)
    minion_id = await _create_minion(minion_repo)
    replace = mocker.patch.object(minion_repo, 'replace_static_extra_data_items')

    await extra_data_service.add_items(_category(is_single_item=True), [minion_id], {'text': 'a'}, is_system=False)

    assert replace.call_args.kwargs['is_system'] is False
    [items] = replace.call_args.args[2].values()
    assert [item['data'] for item in items] == [{'text': 'a'}]


@pytest.mark.asyncio
async def test_system_replace_skips_invalid_and_empty_items(mocked_db, mocker):
    extra_data_service, minion_repo = _build_service(mocked_db)
    minion_id = await _create_minion(minion_repo)
    replace = mocker.patch.object(minion_repo, 'replace_static_extra_data_items')

    await extra_data_service.replace_items(
        _category(), [minion_id], [{'text': 'ok', 'unknown': 1}, {'text': 1}, {}, {'unknown': 1}], is_system=True
    )

    assert replace.call_args.kwargs['is_system'] is True
    [items] = replace.call_args.args[2].values()
    assert [item['data'] for item in items] == [{'text': 'ok'}]


@pytest.mark.asyncio
async def test_system_replace_keeps_last_item_of_single_item_category(mocked_db, mocker):
    extra_data_service, minion_repo = _build_service(mocked_db)
    minion_id = await _create_minion(minion_repo)
    replace = mocker.patch.object(minion_repo, 'replace_static_extra_data_items')

    await extra_data_service.replace_items(
        _category(is_single_item=True), [minion_id], [{'text': 'a'}, {'text': 'b'}], is_system=True
    )

    [items] = replace.call_args.args[2].values()
    assert [item['data'] for item in items] == [{'text': 'b'}]


@pytest.mark.asyncio
async def test_manual_replace_with_many_items_of_single_item_category_is_rejected(mocked_db):
    extra_data_service, minion_repo = _build_service(mocked_db)
    minion_id = await _create_minion(minion_repo)

    with pytest.raises(SaltBoxValidationException):
        await extra_data_service.replace_items(
            _category(is_single_item=True), [minion_id], [{'text': 'a'}, {'text': 'b'}], is_system=False
        )


@pytest.mark.asyncio
async def test_aggregated_category_field_with_data_cannot_be_removed(mocked_db):
    extra_data_service, minion_repo = _build_service(mocked_db)
    minion_id = await _create_minion(minion_repo)
    category = _category('aggregated', minion_fields=['serial'])
    await extra_data_service.add_items(category, [minion_id], {'text': 'Office'}, is_system=True)

    with pytest.raises(SaltBoxValidationException):
        await extra_data_service.remove_category_field(category, 'text')
