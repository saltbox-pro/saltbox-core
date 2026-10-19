import pytest

from saltbox_core.minion_collections.repositories.collection import CollectionRepository
from saltbox_core.minion_collections.services.collection import CollectionService
from saltbox_sdk.db.mongo.schemas_base import PyObjectId


@pytest.fixture
def service(mocked_db, mocker):
    repo = CollectionRepository(mocked_db)
    mocker.patch.object(repo, 'aggregate', mocker.AsyncMock(return_value=[]))

    return CollectionService(repo)


@pytest.mark.asyncio
@pytest.mark.parametrize('search_str', [None, '', 'lin'])
async def test_flat_list_pipeline(service, search_str):
    await service.get_flat_list(search_str)

    pipeline = service.repo.aggregate.await_args.args[0]
    assert pipeline[0] == {'$project': {'slug': 1, 'title': 1, 'description': 1}}
    assert pipeline[-1] == {'$sort': {'title': 1, 'slug': 1}}
    assert len(pipeline) == (3 if search_str else 2)


@pytest.mark.asyncio
async def test_flat_list_items(service):
    collection_id = PyObjectId()
    service.repo.aggregate.return_value = [
        {'_id': collection_id, 'slug': 'linux', 'title': 'Linux', 'description': 'Servers'},
        {'_id': PyObjectId(), 'slug': 'root', 'title': 'Root collection'},
    ]

    items = await service.get_flat_list()

    assert items[0].model_dump(by_alias=True) == {
        'id': collection_id,
        'slug': 'linux',
        'title': 'Linux',
        'description': 'Servers',
    }
    assert items[1].description == ''
