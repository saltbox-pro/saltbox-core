import pytest
from pydantic import ValidationError

from saltbox_core.minion_collections.repositories.extra_data import ExtraDataRepository
from saltbox_core.minion_collections.repositories.extra_data_category import ExtraDataCategoryRepository
from saltbox_core.minion_collections.repositories.minion import MinionRepository
from saltbox_core.minion_collections.schemas.extra_data import ExtraDataCreateSchema
from saltbox_core.minion_collections.schemas.extra_data_category import (
    ExtraDataCategoryCreateRequestSchema,
    ExtraDataCategoryCreateSchema,
    ExtraDataCategoryFieldCreateRequestSchema,
    ExtraDataCategoryFieldsOrderRequestSchema,
    ExtraDataCategoryUpdateSchema,
)
from saltbox_core.minion_collections.schemas.minion import GrainsSchema, MinionCreateSchema
from saltbox_core.minion_collections.services.extra_data import ExtraDataService
from saltbox_core.minion_collections.services.extra_data_category import ExtraDataCategoryService
from saltbox_sdk.event_bus.schemas import (
    ExtraDataCategoryType,
    MinionExtraDataCategoryField,
    MinionExtraDataExtraFieldsPolicy,
)
from saltbox_sdk.exceptions import ObjectNotFoundException, PermissionDeniedException, SaltBoxValidationException


def _build_services(mocked_db):
    category_repo = ExtraDataCategoryRepository(mocked_db)
    extra_data_repo = ExtraDataRepository(mocked_db, extra_data_category_repository=category_repo)
    minion_repo = MinionRepository(mocked_db, extra_data_repository=extra_data_repo)
    extra_data_service = ExtraDataService(extra_data_repo, minion_repo=minion_repo)
    category_service = ExtraDataCategoryService(category_repo, extra_data_service=extra_data_service)

    return category_service, extra_data_service, minion_repo


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

    await category_service.update(
        query=category_id,
        data=ExtraDataCategoryUpdateSchema(extra_fields_policy=MinionExtraDataExtraFieldsPolicy.SAVE_TO_CATEGORY),
    )

    category = await category_service.get(query=category_id)
    assert category.extra_fields_policy == MinionExtraDataExtraFieldsPolicy.SAVE_TO_CATEGORY


@pytest.mark.parametrize('payload', [{'fields': []}, {'minion_fields': []}])
def test_category_fields_are_not_updatable(payload):
    with pytest.raises(ValidationError):
        ExtraDataCategoryUpdateSchema.model_validate(payload)


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
    category_service, extra_data_service, minion_repo = _build_services(mocked_db)

    category_id = await category_service.create(
        ExtraDataCategoryCreateSchema(
            source='manual',
            name='notes',
            type=ExtraDataCategoryType.STATIC,
            fields=[MinionExtraDataCategoryField(name='text', type='str')],
        )
    )
    minion_id = await minion_repo.create(MinionCreateSchema(minion_id='m1', master='master1', grains=GrainsSchema()))

    category = await category_service.get(query=category_id)
    await extra_data_service.add_items(category, [minion_id], {'text': 'hello'}, is_system=False)
    assert (await minion_repo.collection.find_one({'_id': minion_id}))['extra_static']['manual']['notes']

    await category_service.delete(query=category_id)

    assert (await minion_repo.collection.find_one({'_id': minion_id}))['extra_static'] == {'manual': {}}


@pytest.mark.asyncio
async def test_delete_aggregated_category_removes_extra_data_records(mocked_db):
    category_service, extra_data_service, _minion_repo = _build_services(mocked_db)

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
@pytest.mark.parametrize('category_type', [ExtraDataCategoryType.STATIC, ExtraDataCategoryType.AGGREGATED])
async def test_get_manual_data_category(mocked_db, category_type):
    category_service, *_ = _build_services(mocked_db)
    await category_service.create(
        ExtraDataCategoryCreateSchema(source='manual', name='notes', type=category_type, is_manual_data_allowed=True)
    )

    category = await category_service.get_manual_data_category('manual', 'notes')

    assert category.type == category_type


@pytest.mark.asyncio
async def test_get_manual_data_category_rejects_when_not_allowed(mocked_db):
    category_service, *_ = _build_services(mocked_db)
    await category_service.create(
        ExtraDataCategoryCreateSchema(source='manual', name='notes', type=ExtraDataCategoryType.STATIC)
    )

    with pytest.raises(PermissionDeniedException):
        await category_service.get_manual_data_category('manual', 'notes')


async def _create_category(category_service, **kwargs):
    data = {
        'source': 'manual',
        'name': 'notes',
        'type': ExtraDataCategoryType.STATIC,
        'fields': [
            MinionExtraDataCategoryField(name='text', type='str'),
            MinionExtraDataCategoryField(name='author', type='str'),
        ],
        **kwargs,
    }
    return await category_service.create(ExtraDataCategoryCreateSchema(**data))


@pytest.mark.parametrize(
    'payload',
    [
        {'fields': [{'name': 'text', 'type': 'str'}, {'name': 'text', 'type': 'str'}]},
        {'fields': [{'name': 'a.b', 'type': 'str'}]},
        {'fields': [{'name': '$text', 'type': 'str'}]},
    ],
)
def test_create_category_request_rejects_invalid_fields(payload):
    with pytest.raises(SaltBoxValidationException):
        ExtraDataCategoryCreateRequestSchema.model_validate({'name': 'notes', 'type': 'static', **payload})


@pytest.mark.parametrize('field_name', ['a.b', '$text'])
def test_field_create_request_rejects_invalid_name(field_name):
    with pytest.raises(SaltBoxValidationException):
        ExtraDataCategoryFieldCreateRequestSchema.model_validate({'name': field_name, 'type': 'str'})


def test_fields_order_request_rejects_duplicates():
    with pytest.raises(SaltBoxValidationException):
        ExtraDataCategoryFieldsOrderRequestSchema.model_validate({'field_names': ['text', 'text']})


def test_fields_order_request_rejects_empty_list():
    with pytest.raises(ValidationError):
        ExtraDataCategoryFieldsOrderRequestSchema.model_validate({'field_names': []})


@pytest.mark.asyncio
@pytest.mark.parametrize('is_minion_field', [False, True])
async def test_add_field(mocked_db, is_minion_field):
    category_service, *_ = _build_services(mocked_db)
    category_id = await _create_category(category_service)

    await category_service.add_field(
        'manual',
        'notes',
        ExtraDataCategoryFieldCreateRequestSchema(name='room', type='str', is_minion_field=is_minion_field),
    )

    category = await category_service.repo.collection.find_one({'_id': category_id})
    assert [field['name'] for field in category['fields']] == ['text', 'author', 'room']
    assert category['fields'][-1] == {
        'name': 'room',
        'type': 'str',
        'is_empty_allowed': True,
        'is_minion_field': is_minion_field,
    }


@pytest.mark.asyncio
async def test_add_existing_field_is_rejected(mocked_db):
    category_service, *_ = _build_services(mocked_db)
    await _create_category(category_service)

    with pytest.raises(SaltBoxValidationException):
        await category_service.add_field(
            'manual', 'notes', ExtraDataCategoryFieldCreateRequestSchema(name='text', type='str')
        )


@pytest.mark.asyncio
async def test_field_actions_on_system_category_are_forbidden(mocked_db):
    category_service, *_ = _build_services(mocked_db)
    await _create_category(category_service, is_system=True)

    with pytest.raises(PermissionDeniedException):
        await category_service.add_field(
            'manual', 'notes', ExtraDataCategoryFieldCreateRequestSchema(name='room', type='str')
        )
    with pytest.raises(PermissionDeniedException):
        await category_service.delete_field('manual', 'notes', 'text')
    with pytest.raises(PermissionDeniedException):
        await category_service.set_fields_order('manual', 'notes', ['author', 'text'])


@pytest.mark.asyncio
async def test_delete_missing_field_raises_not_found(mocked_db):
    category_service, *_ = _build_services(mocked_db)
    await _create_category(category_service)

    with pytest.raises(ObjectNotFoundException):
        await category_service.delete_field('manual', 'notes', 'room')


@pytest.mark.asyncio
async def test_delete_aggregated_category_field_with_data_is_rejected(mocked_db):
    category_service, extra_data_service, *_ = _build_services(mocked_db)
    category_id = await _create_category(category_service, type=ExtraDataCategoryType.AGGREGATED)
    await extra_data_service.create(
        ExtraDataCreateSchema(source='manual', name='notes', data={'text': 'x', 'author': 'y'}, minions=[])
    )

    with pytest.raises(SaltBoxValidationException):
        await category_service.delete_field('manual', 'notes', 'text')

    category = await category_service.repo.collection.find_one({'_id': category_id})
    assert [field['name'] for field in category['fields']] == ['text', 'author']


@pytest.mark.asyncio
async def test_delete_aggregated_category_field_without_data(mocked_db):
    category_service, *_ = _build_services(mocked_db)
    category_id = await _create_category(category_service, type=ExtraDataCategoryType.AGGREGATED)

    await category_service.delete_field('manual', 'notes', 'text')

    category = await category_service.repo.collection.find_one({'_id': category_id})
    assert [field['name'] for field in category['fields']] == ['author']


@pytest.mark.asyncio
async def test_minion_filter_schema_for_category(mocked_db):
    category_service, *_ = _build_services(mocked_db)
    category_id = await category_service.create(
        ExtraDataCategoryCreateSchema(
            source='manual',
            name='assets',
            type=ExtraDataCategoryType.STATIC,
            fields=[
                MinionExtraDataCategoryField(name='bought_at', type='datetime'),
                MinionExtraDataCategoryField(name='is_laptop', type='bool', is_empty_allowed=False),
                MinionExtraDataCategoryField(name='cores', type='int'),
                MinionExtraDataCategoryField(name='owner', type='str', is_empty_allowed=False),
                MinionExtraDataCategoryField(name='specs', type='dict', is_empty_allowed=False),
            ],
        )
    )

    schema = {
        field.name.removeprefix('extra.manual.assets.'): field.model_dump(by_alias=True)
        for field in await category_service.get_minion_filter_schema_for_category(category_id)
    }

    assert list(schema) == ['bought_at', 'is_laptop', 'cores', 'owner']
    assert schema['bought_at']['inputType'] == 'datetime-local'
    assert schema['bought_at']['valueEditorType'] == 'datetime-local'
    assert [operator['name'] for operator in schema['bought_at']['operators']] == [
        '<',
        '>',
        '<=',
        '>=',
        'null',
        'notNull',
    ]
    assert schema['is_laptop']['valueEditorType'] == 'checkbox'
    assert schema['is_laptop']['defaultValue'] is False
    assert [operator['name'] for operator in schema['is_laptop']['operators']] == ['=']
    assert schema['cores']['inputType'] == 'number'
    assert schema['cores']['valueEditorType'] is None
    assert schema['owner']['inputType'] is None
    assert 'null' not in [operator['name'] for operator in schema['owner']['operators']]
