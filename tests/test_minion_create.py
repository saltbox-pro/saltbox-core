import pytest

from saltbox_core.minion_collections.repositories.collection import CollectionRepository
from saltbox_core.minion_collections.repositories.extra_data import ExtraDataRepository
from saltbox_core.minion_collections.repositories.extra_data_category import ExtraDataCategoryRepository
from saltbox_core.minion_collections.repositories.minion import MinionRepository
from saltbox_core.minion_collections.routers.minion import minion_create
from saltbox_core.minion_collections.schemas.minion import MinionCreateRequestSchema, MinionModel
from saltbox_core.minion_collections.services.minion import MinionService
from saltbox_sdk.exceptions import ObjectNotFoundException

pytestmark = pytest.mark.asyncio


@pytest.fixture
def minion_service(mocked_db, mocker):
    category_repo = ExtraDataCategoryRepository(mocked_db)
    extra_data_repo = ExtraDataRepository(mocked_db, extra_data_category_repository=category_repo)
    service = MinionService(
        MinionRepository(
            mocked_db, extra_data_repository=extra_data_repo, collection_repository=CollectionRepository(mocked_db)
        )
    )

    async def get(query):
        return MinionModel.model_validate(mocked_db['minions'].collection.find_one({'_id': query}))

    mocker.patch.object(service, 'get', get)

    return service


@pytest.fixture
def master_service(mocker):
    service = mocker.MagicMock()
    service.get_by_master_id = mocker.AsyncMock(return_value=mocker.MagicMock(master_id='master1'))

    return service


async def test_minion_create(minion_service, master_service):
    body = MinionCreateRequestSchema(minion_id=' m1 ', master='master1')

    minion = await minion_create(body, minion_service, master_service)

    master_service.get_by_master_id.assert_awaited_once_with('master1')
    assert minion.minion_id == 'm1'
    assert minion.master == 'master1'
    assert minion.last_activity is None
    assert await minion_service.repo.count({}) == 1


async def test_minion_create_unknown_master(minion_service, master_service):
    master_service.get_by_master_id.side_effect = ObjectNotFoundException()
    body = MinionCreateRequestSchema(minion_id='m1', master='unknown')

    with pytest.raises(ObjectNotFoundException):
        await minion_create(body, minion_service, master_service)

    assert await minion_service.repo.count({}) == 0
