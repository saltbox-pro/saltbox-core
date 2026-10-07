import sys

import pytest
from fastapi import HTTPException, status

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
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.db.schemas_base import UserShort


@pytest.fixture
def minion_service(mocked_db, mocker):
    tiq_tasks = mocker.MagicMock()
    tiq_tasks.delete_minion_salt_keys_task.kiq = mocker.AsyncMock()
    mocker.patch.dict(sys.modules, {'saltbox_core.salt.tiq_tasks': tiq_tasks})
    category_repo = ExtraDataCategoryRepository(mocked_db)
    extra_data_repo = ExtraDataRepository(mocked_db, extra_data_category_repository=category_repo)

    return MinionService(MinionRepository(mocked_db, extra_data_repository=extra_data_repo))


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


@pytest.mark.asyncio
async def test_minion_delete(minion_service, collection_service):
    minion_id = await _create_minion(minion_service, 'm1')
    await _create_minion(minion_service, 'm2')

    response = await minion_delete('root', minion_id, minion_service, collection_service)

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert await _minion_ids(minion_service) == {'m2'}


@pytest.mark.asyncio
async def test_minion_delete_outside_collection(minion_service, collection_service):
    minion_id = await _create_minion(minion_service, 'm1', master='master2')

    with pytest.raises(HTTPException) as exc_info:
        await minion_delete('root', minion_id, minion_service, collection_service)

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    assert exc_info.value.detail == 'Minion not found'
    assert await _minion_ids(minion_service) == {'m1'}


@pytest.mark.asyncio
async def test_minion_bulk_delete(minion_service, collection_service):
    first_id = await _create_minion(minion_service, 'm1')
    second_id = await _create_minion(minion_service, 'm2')
    await _create_minion(minion_service, 'm3')
    other_collection_id = await _create_minion(minion_service, 'm4', master='master2')

    body = MinionBulkDeleteBody(
        collection_slug='root', minions=[first_id, second_id, first_id, other_collection_id, PyObjectId()]
    )
    user = UserShort(sub='sub', name='name', email='user@example.com')

    response = await minion_bulk_delete(body, user, minion_service, collection_service)

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert await _minion_ids(minion_service) == {'m3', 'm4'}
