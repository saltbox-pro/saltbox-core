from datetime import UTC, datetime

import pytest
from pymongo.errors import DuplicateKeyError as MongoDuplicateKeyError

from saltbox_core.minion_collections.exceptions import MinionHasBeenActiveException
from saltbox_core.minion_collections.repositories.collection import CollectionRepository
from saltbox_core.minion_collections.repositories.extra_data import ExtraDataRepository
from saltbox_core.minion_collections.repositories.extra_data_category import ExtraDataCategoryRepository
from saltbox_core.minion_collections.repositories.minion import MinionRepository
from saltbox_core.minion_collections.services.minion import MinionService
from saltbox_sdk.exceptions import DuplicateKeyException, ObjectNotFoundException

pytestmark = pytest.mark.asyncio


@pytest.fixture
def minion_service(mocked_db):
    category_repo = ExtraDataCategoryRepository(mocked_db)
    extra_data_repo = ExtraDataRepository(mocked_db, extra_data_category_repository=category_repo)

    return MinionService(
        MinionRepository(
            mocked_db, extra_data_repository=extra_data_repo, collection_repository=CollectionRepository(mocked_db)
        )
    )


@pytest.fixture
def collection(mocker):
    return mocker.MagicMock(full_query={'master': 'master1'})


async def _create_minion(mocked_db, minion_id, *, master='master1', last_activity=None, grains=None):
    result = await mocked_db['minions'].insert_one(
        {'minion_id': minion_id, 'master': master, 'grains': grains or {}, 'last_activity': last_activity}
    )
    return result.inserted_id


def _minion(mocked_db, minion_id):
    return mocked_db['minions'].collection.find_one({'_id': minion_id})


async def test_update_never_active(minion_service, collection, mocked_db):
    minion_id = await _create_minion(mocked_db, 'phantom')

    await minion_service.update_never_active(minion_id, collection, {'minion_id': 'renamed', 'master': 'master2'})

    minion = _minion(mocked_db, minion_id)
    assert (minion['minion_id'], minion['master']) == ('renamed', 'master2')


@pytest.mark.parametrize(
    'minion_fields',
    [{'last_activity': datetime.now(UTC)}, {'grains': {'id': 'phantom'}}],
)
async def test_update_active_minion(minion_service, collection, mocked_db, minion_fields):
    minion_id = await _create_minion(mocked_db, 'phantom', **minion_fields)

    with pytest.raises(MinionHasBeenActiveException):
        await minion_service.update_never_active(minion_id, collection, {'minion_id': 'renamed'})

    assert _minion(mocked_db, minion_id)['minion_id'] == 'phantom'


async def test_update_minion_outside_collection(minion_service, collection, mocked_db):
    minion_id = await _create_minion(mocked_db, 'phantom', master='master2')

    with pytest.raises(ObjectNotFoundException):
        await minion_service.update_never_active(minion_id, collection, {'minion_id': 'renamed'})


async def test_update_duplicate_minion(minion_service, collection, mocked_db, mocker):
    minion_id = await _create_minion(mocked_db, 'phantom')
    error = MongoDuplicateKeyError('duplicate', details={'keyValue': {'minion_id': 'real', 'master': 'master1'}})
    mocker.patch.object(mocked_db['minions'], 'find_one_and_update', mocker.AsyncMock(side_effect=error))

    with pytest.raises(DuplicateKeyException):
        await minion_service.update_never_active(minion_id, collection, {'minion_id': 'real'})


async def test_process_grains_sets_last_activity(minion_service, mocked_db):
    existing_id = await _create_minion(mocked_db, 'existing')

    await minion_service.process_grains('master1', 'existing', {'id': 'existing'})
    await minion_service.process_grains('master1', 'new', {'id': 'new'})

    assert _minion(mocked_db, existing_id)['last_activity'] is not None
    assert mocked_db['minions'].collection.find_one({'minion_id': 'new'})['last_activity'] is not None
