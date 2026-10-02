import pytest

from saltbox_core.minion_collections.repositories.extra_data import ExtraDataRepository
from saltbox_core.minion_collections.repositories.extra_data_category import ExtraDataCategoryRepository
from saltbox_core.minion_collections.repositories.minion import MinionRepository
from saltbox_core.minion_collections.schemas.minion import GrainsSchema, MinionCreateSchema
from saltbox_core.minion_collections.services.minion import MinionService
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.exceptions import ObjectNotFoundException, PermissionDeniedException
from saltbox_sdk.utilities.helpers import utc_now


def _build_minion_service(mocked_db):
    category_repo = ExtraDataCategoryRepository(mocked_db)
    extra_data_repo = ExtraDataRepository(mocked_db, extra_data_category_repository=category_repo)
    minion_repo = MinionRepository(mocked_db, extra_data_repository=extra_data_repo)

    return MinionService(minion_repo), minion_repo


async def _create_minion(minion_repo):
    return await minion_repo.create(MinionCreateSchema(minion_id='m1', master='master1', grains=GrainsSchema()))


@pytest.mark.asyncio
async def test_add_static_extra_data_items(mocked_db):
    minion_service, minion_repo = _build_minion_service(mocked_db)
    first_minion_id = await _create_minion(minion_repo)
    second_minion_id = await minion_repo.create(
        MinionCreateSchema(minion_id='m2', master='master1', grains=GrainsSchema())
    )

    items = await minion_service.add_static_extra_data_items(
        [first_minion_id, second_minion_id], 'manual', 'notes', {'text': 'hello'}, replace_manual=False
    )

    assert {item['minion_id'] for item in items} == {first_minion_id, second_minion_id}
    assert items[0]['_id'] != items[1]['_id']

    for item in items:
        assert item['is_system'] is False
        stored = await minion_repo.get_static_extra_data_item(item['minion_id'], 'manual', 'notes', item['_id'])
        assert stored is not None
        assert stored['data'] == {'text': 'hello'}


@pytest.mark.asyncio
async def test_add_static_extra_data_items_skips_missing_minions(mocked_db):
    minion_service, minion_repo = _build_minion_service(mocked_db)
    minion_id = await _create_minion(minion_repo)

    items = await minion_service.add_static_extra_data_items(
        [minion_id, PyObjectId()], 'manual', 'notes', {'text': 'hello'}, replace_manual=False
    )

    assert [item['minion_id'] for item in items] == [minion_id]


@pytest.mark.asyncio
async def test_add_static_extra_data_items_to_missing_minions(mocked_db):
    minion_service, _minion_repo = _build_minion_service(mocked_db)

    items = await minion_service.add_static_extra_data_items(
        [PyObjectId()], 'manual', 'notes', {'text': 'hello'}, replace_manual=False
    )

    assert items == []


@pytest.mark.asyncio
async def test_delete_manual_static_extra_data_item(mocked_db):
    minion_service, minion_repo = _build_minion_service(mocked_db)
    minion_id = await _create_minion(minion_repo)

    [item] = await minion_service.add_static_extra_data_items(
        [minion_id], 'manual', 'notes', {'text': 'hello'}, replace_manual=False
    )
    await minion_service.delete_static_extra_data_item(minion_id, 'manual', 'notes', item['_id'])

    assert await minion_repo.get_static_extra_data_item(minion_id, 'manual', 'notes', item['_id']) is None


@pytest.mark.asyncio
async def test_cannot_delete_system_item(mocked_db):
    minion_service, minion_repo = _build_minion_service(mocked_db)
    minion_id = await _create_minion(minion_repo)

    system_item = {'_id': PyObjectId(), 'is_system': True, 'updated_at': utc_now(), 'data': {'model': 'x86'}}
    await minion_repo.add_static_extra_data_items('inventory', 'cpu', {minion_id: system_item}, replace_manual=False)

    with pytest.raises(PermissionDeniedException):
        await minion_service.delete_static_extra_data_item(minion_id, 'inventory', 'cpu', system_item['_id'])

    assert await minion_repo.get_static_extra_data_item(minion_id, 'inventory', 'cpu', system_item['_id'])


@pytest.mark.asyncio
async def test_delete_missing_item_raises_not_found(mocked_db):
    minion_service, minion_repo = _build_minion_service(mocked_db)
    minion_id = await _create_minion(minion_repo)

    with pytest.raises(ObjectNotFoundException):
        await minion_service.delete_static_extra_data_item(minion_id, 'manual', 'notes', PyObjectId())
