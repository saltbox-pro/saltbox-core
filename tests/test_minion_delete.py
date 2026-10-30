import sys

import pytest
from fastapi import HTTPException, status

from saltbox_core.minion_collections.repositories.collection import CollectionRepository
from saltbox_core.minion_collections.repositories.extra_data import ExtraDataRepository
from saltbox_core.minion_collections.repositories.extra_data_category import ExtraDataCategoryRepository
from saltbox_core.minion_collections.repositories.minion import MinionRepository
from saltbox_core.minion_collections.routers.minion import minion_bulk_delete, minion_delete
from saltbox_core.minion_collections.schemas.minion import (
    GrainsSchema,
    MinionBulkDeleteBody,
    MinionCreateSchema,
    MinionTgtOnlySchema,
)
from saltbox_core.minion_collections.services.minion import MinionService
from saltbox_core.tasks.repositories.tasks_minion import TaskMinionRepository
from saltbox_core.tasks.services.tasks_minion import TaskMinionService
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.db.schemas_base import UserShort


@pytest.fixture
def tiq_tasks(mocker):
    tiq_tasks = mocker.MagicMock()
    tiq_tasks.delete_minion_salt_keys_task.kiq = mocker.AsyncMock()
    mocker.patch.dict(sys.modules, {'saltbox_core.salt.tiq_tasks': tiq_tasks})

    return tiq_tasks


@pytest.fixture
def task_minion_service(mocked_db, mocker):
    return TaskMinionService(repo=TaskMinionRepository(mocked_db), rdb=mocker.MagicMock())


@pytest.fixture
def minion_service(mocked_db, tiq_tasks):
    category_repo = ExtraDataCategoryRepository(mocked_db)
    extra_data_repo = ExtraDataRepository(mocked_db, extra_data_category_repository=category_repo)

    return MinionService(
        MinionRepository(
            mocked_db, extra_data_repository=extra_data_repo, collection_repository=CollectionRepository(mocked_db)
        )
    )


@pytest.fixture
def collection_service(mocker):
    service = mocker.MagicMock()
    service.get_by_slug = mocker.AsyncMock(return_value=mocker.MagicMock(full_query={'master': 'master1'}))

    return service


async def _create_minion(minion_service, minion_id, master='master1'):
    return await minion_service.repo.create(
        MinionCreateSchema(minion_id=minion_id, master=master, grains=GrainsSchema())
    )


async def _minion_ids(minion_service):
    return {minion.minion_id for minion in await minion_service.get_list({}, projection_model=MinionTgtOnlySchema)}


def _add_refs(mocked_db, *minion_ids):
    for minion_id in minion_ids:
        mocked_db['task_minions'].collection.insert_one({'task_id': PyObjectId(), 'minion_inner_id': minion_id})
    mocked_db['minion_extra_data'].collection.insert_one(
        {
            'source': 'manual',
            'name': 'software',
            'data': {'name': 'vim'},
            'minions': [{'_id': PyObjectId(), 'minion_id': minion_id, 'is_system': False} for minion_id in minion_ids],
        }
    )


def _refs(mocked_db):
    task_minion_ids = [doc['minion_inner_id'] for doc in mocked_db['task_minions'].collection.find()]
    extra_minion_ids = [
        entry['minion_id'] for doc in mocked_db['minion_extra_data'].collection.find() for entry in doc['minions']
    ]
    return task_minion_ids, extra_minion_ids


@pytest.mark.asyncio
async def test_minion_delete(minion_service, collection_service, task_minion_service, tiq_tasks, mocked_db):
    minion_id = await _create_minion(minion_service, 'm1')
    other_id = await _create_minion(minion_service, 'm2')
    _add_refs(mocked_db, minion_id, other_id)

    response = await minion_delete('root', minion_id, minion_service, collection_service, task_minion_service)

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert await _minion_ids(minion_service) == {'m2'}
    assert _refs(mocked_db) == ([other_id], [other_id])
    tiq_tasks.delete_minion_salt_keys_task.kiq.assert_awaited_once_with(minion_id='m1', master_id='master1')


@pytest.mark.asyncio
async def test_minion_delete_outside_collection(minion_service, collection_service, task_minion_service):
    minion_id = await _create_minion(minion_service, 'm1', master='master2')

    with pytest.raises(HTTPException) as exc_info:
        await minion_delete('root', minion_id, minion_service, collection_service, task_minion_service)

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    assert exc_info.value.detail == 'Minion not found'
    assert await _minion_ids(minion_service) == {'m1'}


@pytest.mark.asyncio
async def test_minion_bulk_delete(minion_service, collection_service, task_minion_service, mocked_db):
    first_id = await _create_minion(minion_service, 'm1')
    second_id = await _create_minion(minion_service, 'm2')
    kept_id = await _create_minion(minion_service, 'm3')
    other_collection_id = await _create_minion(minion_service, 'm4', master='master2')
    _add_refs(mocked_db, first_id, second_id, kept_id, other_collection_id)

    body = MinionBulkDeleteBody(
        collection_slug='root', minions=[first_id, second_id, first_id, other_collection_id, PyObjectId()]
    )
    user = UserShort(sub='sub', name='name', email='user@example.com')

    response = await minion_bulk_delete(body, user, minion_service, collection_service, task_minion_service)

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert await _minion_ids(minion_service) == {'m3', 'm4'}
    assert _refs(mocked_db) == ([kept_id, other_collection_id], [kept_id, other_collection_id])
