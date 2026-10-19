import pytest

from saltbox_core.minion_collections.repositories.collection import CollectionRepository
from saltbox_core.minion_collections.services.collection import CollectionService
from saltbox_sdk.db.mongo.schemas_base import PyObjectId


@pytest.fixture
def service(mocked_db, mocker):
    repo = CollectionRepository(mocked_db)
    mocker.patch.object(repo, 'aggregate', mocker.AsyncMock(return_value=[]))

    return CollectionService(repo)


PROJECT_AND_SORT = [
    {'$project': {'slug': 1, 'title': 1, 'description': 1, 'parent_id': 1}},
    {'$sort': {'title': 1, 'slug': 1}},
]


@pytest.mark.asyncio
@pytest.mark.parametrize('search_str', [None, ''])
async def test_flat_list_pipeline_without_search(service, search_str):
    await service.get_flat_list(search_str)

    assert service.repo.aggregate.await_args.args[0] == [{'$match': {}}, *PROJECT_AND_SORT]


@pytest.mark.asyncio
async def test_flat_list_pipeline_searches_only_slug_title_description(service):
    await service.get_flat_list('a.b')

    search = {'$regex': r'a\.b', '$options': 'i'}
    assert service.repo.aggregate.await_args.args[0] == [
        {'$match': {'$or': [{'slug': search}, {'title': search}, {'description': search}]}},
        *PROJECT_AND_SORT,
    ]


@pytest.mark.asyncio
async def test_flat_list_items(service):
    collection_id = PyObjectId()
    root_id = PyObjectId()
    service.repo.aggregate.return_value = [
        {'_id': collection_id, 'slug': 'linux', 'title': 'Linux', 'description': 'Servers', 'parent_id': root_id},
        {'_id': PyObjectId(), 'slug': 'root', 'title': 'Root collection'},
    ]

    items = await service.get_flat_list()

    assert items[0].model_dump(by_alias=True) == {
        'id': collection_id,
        'slug': 'linux',
        'title': 'Linux',
        'description': 'Servers',
        'parent_id': root_id,
    }
    assert items[1].description == ''
    assert items[1].parent_id is None
