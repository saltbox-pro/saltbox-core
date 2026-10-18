from datetime import datetime

import pytest

from saltbox_core.minion_collections.exceptions import CyclicCollectionReferenceException
from saltbox_core.minion_collections.repositories.collection import CollectionRepository
from saltbox_core.minion_collections.repositories.extra_data import ExtraDataRepository
from saltbox_core.minion_collections.repositories.extra_data_category import ExtraDataCategoryRepository
from saltbox_core.minion_collections.repositories.minion import MinionRepository
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.exceptions import SaltBoxValidationException

pytestmark = pytest.mark.asyncio

LINUX_QUERY = {'grains.kernel': 'Linux'}
ALT_QUERY = {'grains.os': 'ALT'}


@pytest.fixture
def collection_repo(mocked_db):
    return CollectionRepository(mocked_db)


@pytest.fixture
def minion_repo(mocked_db, collection_repo):
    category_repo = ExtraDataCategoryRepository(mocked_db)
    extra_data_repo = ExtraDataRepository(mocked_db, extra_data_category_repository=category_repo)

    return MinionRepository(mocked_db, extra_data_repository=extra_data_repo, collection_repository=collection_repo)


@pytest.fixture
def add_collection(collection_repo):
    return lambda slug, query, parent_id=None: insert_collection(collection_repo, slug, query, parent_id)


async def insert_collection(repo, slug, query, parent_id=None):
    if parent_id is None and slug != 'root':
        root = await repo.collection.find_one(filter={'slug': 'root'}) or {}
        parent_id = root.get('_id') or await insert_collection(repo, 'root', {})

    document = {'parent_id': parent_id, 'title': slug, 'slug': slug, 'query': query, 'order': 0, 'owner_id': 'u1'}
    result = await repo.collection.insert_one(document=document)
    return PyObjectId(result.inserted_id)


async def test_collection_in_expands_to_or(minion_repo, add_collection):
    await add_collection('linux', LINUX_QUERY)
    await add_collection('alt', ALT_QUERY)

    query = await minion_repo.__prepare_query__({'collection': {'$in': ['linux', 'alt']}})

    assert query == {'$or': [LINUX_QUERY, ALT_QUERY]}


async def test_collection_nin_expands_to_nor(minion_repo, add_collection):
    await add_collection('linux', LINUX_QUERY)

    query = await minion_repo.__prepare_query__({'collection': {'$nin': ['linux']}})

    assert query == {'$nor': [LINUX_QUERY]}


async def test_collection_filter_inside_and(minion_repo, add_collection):
    await add_collection('linux', LINUX_QUERY)

    query = await minion_repo.__prepare_query__({'$and': [{'master': 'm1'}, {'collection': {'$in': ['linux']}}]})

    assert query == {'$and': [{'master': 'm1'}, {'$or': [LINUX_QUERY]}]}


async def test_collection_full_query_includes_parent(minion_repo, add_collection):
    linux_id = await add_collection('linux', LINUX_QUERY)
    await add_collection('alt', ALT_QUERY, parent_id=linux_id)

    query = await minion_repo.__prepare_query__({'collection': {'$in': ['alt']}})

    assert query == {'$or': [{'$and': [LINUX_QUERY, ALT_QUERY]}]}


async def test_nested_collection_filter_is_expanded(minion_repo, add_collection):
    await add_collection('alt', ALT_QUERY)
    await add_collection('nested', {'$and': [{'master': 'm1'}, {'collection': {'$nin': ['alt']}}]})

    query = await minion_repo.__prepare_query__({'collection': {'$in': ['nested']}})

    assert query == {'$or': [{'$and': [{'master': 'm1'}, {'$nor': [ALT_QUERY]}]}]}


async def test_expanded_query_is_prepared_by_other_overrides(minion_repo, add_collection):
    await add_collection('active', {'last_activity_seconds': {'$lt': 60}})

    query = await minion_repo.__prepare_query__({'collection': {'$in': ['active']}})

    assert list(query['$or'][0]) == ['last_activity']
    assert isinstance(query['$or'][0]['last_activity']['$gt'], datetime)


@pytest.mark.parametrize(
    ('raw_query', 'expected'),
    [
        ({'collection': {'$in': []}}, {'_id': {'$in': []}}),
        ({'collection': {'$in': ['unknown']}}, {'_id': {'$in': []}}),
        ({'collection': {'$nin': []}}, {}),
        ({'collection': {'$nin': ['unknown']}}, {}),
    ],
)
async def test_empty_or_unknown_collections(minion_repo, raw_query, expected):
    assert await minion_repo.__prepare_query__(raw_query) == expected


@pytest.mark.parametrize(
    'value',
    [
        'linux',
        ['linux'],
        {'$eq': 'linux'},
        {'$in': 'linux'},
        {'$in': [1]},
        {'$in': ['linux'], '$nin': ['alt']},
    ],
)
async def test_unsupported_values(minion_repo, value):
    with pytest.raises(SaltBoxValidationException):
        await minion_repo.__prepare_query__({'collection': value})


async def test_self_reference(minion_repo, add_collection):
    await add_collection('self-ref', {'collection': {'$in': ['self-ref']}})

    with pytest.raises(CyclicCollectionReferenceException) as exc_info:
        await minion_repo.__prepare_query__({'collection': {'$in': ['self-ref']}})

    assert exc_info.value.slugs == ['self-ref', 'self-ref']


async def test_cyclic_reference(minion_repo, add_collection):
    await add_collection('a', {'collection': {'$nin': ['b']}})
    await add_collection('b', {'collection': {'$in': ['c']}})
    await add_collection('c', {'collection': {'$in': ['b']}})

    with pytest.raises(CyclicCollectionReferenceException) as exc_info:
        await minion_repo.__prepare_query__({'collection': {'$in': ['a']}})

    assert exc_info.value.slugs == ['b', 'c', 'b']
