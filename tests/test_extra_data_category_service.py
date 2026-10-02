import pytest
from pydantic import ValidationError

from saltbox_core.minion_collections.repositories.extra_data import ExtraDataRepository
from saltbox_core.minion_collections.repositories.extra_data_category import ExtraDataCategoryRepository
from saltbox_core.minion_collections.repositories.minion import MinionRepository
from saltbox_core.minion_collections.schemas.extra_data import ExtraDataCreateSchema
from saltbox_core.minion_collections.schemas.extra_data_category import (
    ExtraDataCategoryCreateSchema,
    ExtraDataCategoryUpdateSchema,
)
from saltbox_core.minion_collections.schemas.minion import GrainsSchema, MinionCreateSchema
from saltbox_core.minion_collections.services.extra_data import ExtraDataService
from saltbox_core.minion_collections.services.extra_data_category import ExtraDataCategoryService
from saltbox_core.minion_collections.services.minion import MinionService
from saltbox_sdk.event_bus.schemas import ExtraDataCategoryType
from saltbox_sdk.exceptions import PermissionDeniedException, SaltBoxValidationException


def _build_services(mocked_db):
    category_repo = ExtraDataCategoryRepository(mocked_db)
    extra_data_repo = ExtraDataRepository(mocked_db, extra_data_category_repository=category_repo)
    extra_data_service = ExtraDataService(extra_data_repo)
    minion_repo = MinionRepository(mocked_db, extra_data_repository=extra_data_repo)
    minion_service = MinionService(minion_repo)
    category_service = ExtraDataCategoryService(
        category_repo, extra_data_service=extra_data_service, minion_service=minion_service
    )

    return category_service, extra_data_service, minion_service, minion_repo


@pytest.mark.asyncio
async def test_update_system_category_is_forbidden(mocked_db):
    category_service, *_ = _build_services(mocked_db)

    category_id = await category_service.create(
        ExtraDataCategoryCreateSchema(source='inventory', name='cpu', type=ExtraDataCategoryType.STATIC, is_system=True)
    )

    with pytest.raises(PermissionDeniedException):
        await category_service.update(query=category_id, data=ExtraDataCategoryUpdateSchema())


@pytest.mark.asyncio
async def test_delete_system_category_is_forbidden(mocked_db):
    category_service, *_ = _build_services(mocked_db)

    category_id = await category_service.create(
        ExtraDataCategoryCreateSchema(source='inventory', name='cpu', type=ExtraDataCategoryType.STATIC, is_system=True)
    )

    with pytest.raises(PermissionDeniedException):
        await category_service.delete(query=category_id)


@pytest.mark.asyncio
async def test_update_manual_category_is_allowed(mocked_db):
    category_service, *_ = _build_services(mocked_db)

    category_id = await category_service.create(
        ExtraDataCategoryCreateSchema(source='manual', name='notes', type=ExtraDataCategoryType.STATIC)
    )

    await category_service.update(query=category_id, data=ExtraDataCategoryUpdateSchema(minion_fields=['foo']))

    category = await category_service.get(query=category_id)
    assert category.minion_fields == ['foo']


@pytest.mark.asyncio
async def test_update_manual_category_title_description_icon(mocked_db):
    category_service, *_ = _build_services(mocked_db)

    category_id = await category_service.create(
        ExtraDataCategoryCreateSchema(
            source='manual', name='notes', type=ExtraDataCategoryType.STATIC, is_single_item=True
        )
    )
    category = await category_service.get(query=category_id)
    assert category.title is None
    assert category.is_single_item is True

    await category_service.update(
        query=category_id,
        data=ExtraDataCategoryUpdateSchema(
            title={'ru': 'Заметки', 'en': 'Notes'}, description={'en': 'Manual notes'}, icon='note'
        ),
    )

    category = await category_service.get(query=category_id)
    assert category.title == {'ru': 'Заметки', 'en': 'Notes'}
    assert category.description == {'en': 'Manual notes'}
    assert category.icon == 'note'
    assert category.is_single_item is True


def test_is_single_item_is_not_updatable():
    with pytest.raises(ValidationError):
        ExtraDataCategoryUpdateSchema.model_validate({'is_single_item': True})


@pytest.mark.asyncio
async def test_delete_static_category_removes_minion_data(mocked_db):
    category_service, _extra_data_service, minion_service, minion_repo = _build_services(mocked_db)

    category_id = await category_service.create(
        ExtraDataCategoryCreateSchema(source='manual', name='notes', type=ExtraDataCategoryType.STATIC)
    )
    minion_id = await minion_repo.create(MinionCreateSchema(minion_id='m1', master='master1', grains=GrainsSchema()))

    await minion_service.add_static_extra_data_items(
        [minion_id], 'manual', 'notes', {'text': 'hello'}, replace_manual=False
    )
    assert (await minion_repo.collection.find_one({'_id': minion_id}))['extra_static']['manual']['notes']

    await category_service.delete(query=category_id)

    assert (await minion_repo.collection.find_one({'_id': minion_id}))['extra_static'] == {'manual': {}}


@pytest.mark.asyncio
async def test_delete_aggregated_category_removes_extra_data_records(mocked_db):
    category_service, extra_data_service, _minion_service, _minion_repo = _build_services(mocked_db)

    category_id = await category_service.create(
        ExtraDataCategoryCreateSchema(source='manual', name='tags', type=ExtraDataCategoryType.AGGREGATED)
    )
    await extra_data_service.create(
        ExtraDataCreateSchema(source='manual', name='tags', data={'tag': 'prod'}, minions=[])
    )

    assert await extra_data_service.count({'source': 'manual', 'name': 'tags'}) == 1

    await category_service.delete(query=category_id)

    assert await extra_data_service.count({'source': 'manual', 'name': 'tags'}) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('category_type', 'is_manual_data_allowed', 'expected_exception'),
    [
        (ExtraDataCategoryType.AGGREGATED, True, SaltBoxValidationException),
        (ExtraDataCategoryType.STATIC, False, PermissionDeniedException),
    ],
)
async def test_get_manual_static_category_rejects(mocked_db, category_type, is_manual_data_allowed, expected_exception):
    category_service, *_ = _build_services(mocked_db)
    await category_service.create(
        ExtraDataCategoryCreateSchema(
            source='manual', name='notes', type=category_type, is_manual_data_allowed=is_manual_data_allowed
        )
    )

    with pytest.raises(expected_exception):
        await category_service.get_manual_static_category('manual', 'notes')
