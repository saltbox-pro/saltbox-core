from datetime import UTC, datetime

import pytest

from saltbox_core.minion_collections.exceptions import (
    MinionHasBeenActiveException,
    MinionMergeConflictException,
    MinionMergeIntoItselfException,
)
from saltbox_core.minion_collections.repositories.collection import CollectionRepository
from saltbox_core.minion_collections.repositories.extra_data import ExtraDataRepository
from saltbox_core.minion_collections.repositories.extra_data_category import ExtraDataCategoryRepository
from saltbox_core.minion_collections.repositories.minion import MinionRepository
from saltbox_core.minion_collections.routers.minion import minion_merge
from saltbox_core.minion_collections.schemas.minion import (
    MinionMergeBody,
    MinionMergeConflictStrategy,
    MinionMergeExtraDataStrategy,
    MinionModel,
)
from saltbox_core.minion_collections.services.minion import MinionService
from saltbox_core.tasks.repositories.tasks_minion import TaskMinionRepository
from saltbox_core.tasks.services.tasks_minion import TaskMinionService
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.exceptions import ObjectNotFoundException

pytestmark = pytest.mark.asyncio


@pytest.fixture
def minion_service(mocked_db, mocker):
    category_repo = ExtraDataCategoryRepository(mocked_db)
    extra_data_repo = ExtraDataRepository(mocked_db, extra_data_category_repository=category_repo)
    mocker.patch.object(extra_data_repo, 'move_minion_entries', mocker.AsyncMock())

    return MinionService(
        MinionRepository(
            mocked_db, extra_data_repository=extra_data_repo, collection_repository=CollectionRepository(mocked_db)
        )
    )


@pytest.fixture
def collection(mocker):
    return mocker.MagicMock(full_query={'master': 'master1'})


@pytest.fixture
def single_item_category(mocked_db):
    mocked_db['minion_extra_data_category'].collection.insert_one(
        {
            'source': 'manual',
            'name': 'owner',
            'type': 'static',
            'is_single_item': True,
            'fields': [],
            'created': datetime.now(UTC),
            'modified': datetime.now(UTC),
        }
    )


def _item(name, *, is_system=False):
    return {'_id': PyObjectId(), 'is_system': is_system, 'data': {'name': name}}


async def _create_minion(mocked_db, minion_id, *, extra_static=None, last_activity=None, grains=None):
    result = await mocked_db['minions'].insert_one(
        {
            'minion_id': minion_id,
            'master': 'master1',
            'grains': grains or {},
            'extra_static': extra_static or {},
            'last_activity': last_activity,
            'created': datetime.now(UTC),
            'modified': datetime.now(UTC),
        }
    )
    return result.inserted_id


def _static_names(mocked_db, minion_id, source, name):
    doc = mocked_db['minions'].collection.find_one({'_id': minion_id})
    return [item['data']['name'] for item in doc['extra_static'].get(source, {}).get(name, [])]


def _add_aggregated(mocked_db, minion_id, *, is_system):
    mocked_db['minion_extra_data'].collection.insert_one(
        {
            'source': 'manual',
            'name': 'software',
            'data': {'name': 'vim'},
            'minions': [{'_id': PyObjectId(), 'minion_id': minion_id, 'is_system': is_system, 'data': {}}],
        }
    )


def _aggregated_minion_ids(mocked_db):
    return [entry['minion_id'] for doc in mocked_db['minion_extra_data'].collection.find() for entry in doc['minions']]


async def _merge(minion_service, source_id, target_id, collection, extra_data_strategy, conflict_strategy):
    await minion_service.merge(
        source_id,
        target_id,
        collection,
        extra_data_strategy=extra_data_strategy,
        conflict_strategy=conflict_strategy,
    )


async def test_merge_appends_source_items(minion_service, collection, mocked_db, single_item_category):
    source_id = await _create_minion(mocked_db, 'phantom', extra_static={'manual': {'notes': [_item('source')]}})
    target_id = await _create_minion(
        mocked_db,
        'real',
        extra_static={'manual': {'notes': [_item('target')]}},
        last_activity=datetime.now(UTC),
        grains={'id': 'real'},
    )
    _add_aggregated(mocked_db, source_id, is_system=False)

    await _merge(
        minion_service,
        source_id,
        target_id,
        collection,
        MinionMergeExtraDataStrategy.MERGE,
        MinionMergeConflictStrategy.ERROR,
    )

    assert _static_names(mocked_db, target_id, 'manual', 'notes') == ['target', 'source']
    assert mocked_db['minions'].collection.find_one({'_id': source_id}) is None
    minion_service.repo.extra_data_repository.move_minion_entries.assert_awaited_once_with(
        source_id, target_id, excluded_categories=[], session=None
    )
    assert _aggregated_minion_ids(mocked_db) == []


async def test_merge_conflict_error(minion_service, collection, mocked_db, single_item_category):
    owner = {'manual': {'owner': [_item('source')]}}
    source_id = await _create_minion(mocked_db, 'phantom', extra_static=owner)
    target_id = await _create_minion(mocked_db, 'real', extra_static={'manual': {'owner': [_item('target')]}})

    with pytest.raises(MinionMergeConflictException) as exc_info:
        await _merge(
            minion_service,
            source_id,
            target_id,
            collection,
            MinionMergeExtraDataStrategy.MERGE,
            MinionMergeConflictStrategy.ERROR,
        )

    assert exc_info.value.categories == ['manual.owner']
    assert mocked_db['minions'].collection.find_one({'_id': source_id}) is not None
    assert _static_names(mocked_db, target_id, 'manual', 'owner') == ['target']


async def test_merge_conflict_use_source(minion_service, collection, mocked_db, single_item_category):
    source_id = await _create_minion(mocked_db, 'phantom', extra_static={'manual': {'owner': [_item('source')]}})
    target_id = await _create_minion(
        mocked_db,
        'real',
        extra_static={'manual': {'owner': [_item('system', is_system=True), _item('target')]}},
    )

    await _merge(
        minion_service,
        source_id,
        target_id,
        collection,
        MinionMergeExtraDataStrategy.MERGE,
        MinionMergeConflictStrategy.USE_SOURCE,
    )

    assert _static_names(mocked_db, target_id, 'manual', 'owner') == ['system', 'source']


async def test_merge_conflict_use_target(minion_service, collection, mocked_db, single_item_category):
    source_id = await _create_minion(
        mocked_db,
        'phantom',
        extra_static={'manual': {'owner': [_item('source')], 'notes': [_item('source note')]}},
    )
    target_id = await _create_minion(mocked_db, 'real', extra_static={'manual': {'owner': [_item('target')]}})

    await _merge(
        minion_service,
        source_id,
        target_id,
        collection,
        MinionMergeExtraDataStrategy.MERGE,
        MinionMergeConflictStrategy.USE_TARGET,
    )

    assert _static_names(mocked_db, target_id, 'manual', 'owner') == ['target']
    assert _static_names(mocked_db, target_id, 'manual', 'notes') == ['source note']
    minion_service.repo.extra_data_repository.move_minion_entries.assert_awaited_once_with(
        source_id, target_id, excluded_categories=[('manual', 'owner')], session=None
    )


async def test_merge_use_source_replaces_all_target_manual_items(minion_service, collection, mocked_db):
    source_id = await _create_minion(mocked_db, 'phantom', extra_static={'manual': {'notes': [_item('source')]}})
    target_id = await _create_minion(
        mocked_db,
        'real',
        extra_static={
            'manual': {'notes': [_item('target')], 'tags': [_item('tag'), _item('system tag', is_system=True)]}
        },
    )
    _add_aggregated(mocked_db, target_id, is_system=False)
    _add_aggregated(mocked_db, target_id, is_system=True)

    await _merge(
        minion_service,
        source_id,
        target_id,
        collection,
        MinionMergeExtraDataStrategy.USE_SOURCE,
        MinionMergeConflictStrategy.ERROR,
    )

    assert _static_names(mocked_db, target_id, 'manual', 'notes') == ['source']
    assert _static_names(mocked_db, target_id, 'manual', 'tags') == ['system tag']
    assert _aggregated_minion_ids(mocked_db) == [target_id]


async def test_merge_use_target_keeps_target_data(minion_service, collection, mocked_db):
    source_id = await _create_minion(mocked_db, 'phantom', extra_static={'manual': {'notes': [_item('source')]}})
    target_id = await _create_minion(mocked_db, 'real', extra_static={'manual': {'notes': [_item('target')]}})
    _add_aggregated(mocked_db, source_id, is_system=False)

    await _merge(
        minion_service,
        source_id,
        target_id,
        collection,
        MinionMergeExtraDataStrategy.USE_TARGET,
        MinionMergeConflictStrategy.ERROR,
    )

    assert _static_names(mocked_db, target_id, 'manual', 'notes') == ['target']
    minion_service.repo.extra_data_repository.move_minion_entries.assert_not_awaited()
    assert _aggregated_minion_ids(mocked_db) == []
    assert mocked_db['minions'].collection.find_one({'_id': source_id}) is None


@pytest.mark.parametrize(
    'source_fields',
    [{'last_activity': datetime.now(UTC)}, {'grains': {'id': 'phantom'}}],
)
async def test_merge_active_source(minion_service, collection, mocked_db, source_fields):
    source_id = await _create_minion(mocked_db, 'phantom', **source_fields)
    target_id = await _create_minion(mocked_db, 'real')

    with pytest.raises(MinionHasBeenActiveException):
        await _merge(
            minion_service,
            source_id,
            target_id,
            collection,
            MinionMergeExtraDataStrategy.MERGE,
            MinionMergeConflictStrategy.ERROR,
        )


async def test_merge_into_itself(minion_service, collection, mocked_db):
    minion_id = await _create_minion(mocked_db, 'phantom')

    with pytest.raises(MinionMergeIntoItselfException):
        await _merge(
            minion_service,
            minion_id,
            minion_id,
            collection,
            MinionMergeExtraDataStrategy.MERGE,
            MinionMergeConflictStrategy.ERROR,
        )


async def test_merge_target_outside_collection(minion_service, collection, mocked_db):
    source_id = await _create_minion(mocked_db, 'phantom')
    target_id = (
        await mocked_db['minions'].insert_one({'minion_id': 'real', 'master': 'master2', 'grains': {}})
    ).inserted_id

    with pytest.raises(ObjectNotFoundException):
        await _merge(
            minion_service,
            source_id,
            target_id,
            collection,
            MinionMergeExtraDataStrategy.MERGE,
            MinionMergeConflictStrategy.ERROR,
        )


async def test_merge_route_deletes_source_task_minions(minion_service, collection, mocked_db, mocker):
    source_id = await _create_minion(mocked_db, 'phantom')
    target_id = await _create_minion(mocked_db, 'real')
    for minion_id in (source_id, target_id):
        mocked_db['task_minions'].collection.insert_one({'task_id': PyObjectId(), 'minion_inner_id': minion_id})

    original_get = minion_service.get

    async def get(query, **kwargs):
        if kwargs:
            return await original_get(query, **kwargs)
        return MinionModel.model_validate(mocked_db['minions'].collection.find_one({'_id': query}))

    mocker.patch.object(minion_service, 'get', get)
    collection_service = mocker.MagicMock()
    collection_service.get_by_slug = mocker.AsyncMock(return_value=collection)
    task_minion_service = TaskMinionService(repo=TaskMinionRepository(mocked_db), rdb=mocker.MagicMock())

    minion = await minion_merge(
        MinionMergeBody(collection_slug='root', source_id=source_id, target_id=target_id),
        minion_service,
        collection_service,
        task_minion_service,
    )

    assert minion.id == target_id
    task_minion_ids = [doc['minion_inner_id'] for doc in mocked_db['task_minions'].collection.find()]
    assert task_minion_ids == [target_id]
