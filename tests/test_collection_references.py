import pytest

from saltbox_core.minion_collections.exceptions import (
    CyclicCollectionReferenceException,
    ReferencedCollectionDeleteException,
    UnknownCollectionReferenceException,
)
from saltbox_core.minion_collections.repositories.collection import CollectionRepository
from saltbox_core.minion_collections.schemas.collection import CollectionCreateSchema, CollectionUpdateSchema
from saltbox_core.minion_collections.services.collection import CollectionService
from saltbox_core.minion_collections.utils.collection_filter import find_cycle, get_referenced_slugs
from saltbox_sdk.exceptions import SaltBoxValidationException


def _in(*slugs):
    return {'collection': {'$in': list(slugs)}}


@pytest.fixture
def service(mocked_db):
    return CollectionService(CollectionRepository(mocked_db))


@pytest.fixture
def create(service):
    async def create(title, query=None, parent_id=None):
        if parent_id is None:
            root = await service.repo.collection.find_one(filter={'slug': 'root'})
            parent_id = (
                root['_id']
                if root
                else await service.repo.create(
                    CollectionCreateSchema(title='Root', slug='root', query={}, owner_id='user1')
                )
            )

        return await service.create(
            CollectionCreateSchema(title=title, query=query or {}, parent_id=parent_id, owner_id='user1')
        )

    return create


async def _update_query(service, slug, query):
    return await service.update_by_slug(slug, CollectionUpdateSchema(title=slug, query=query))


# Utils


@pytest.mark.parametrize(
    ('query', 'expected'),
    [
        ({}, set()),
        ({'grains.os': 'ALT'}, set()),
        (_in('alpha', 'bravo'), {'alpha', 'bravo'}),
        ({'$and': [_in('alpha'), {'$or': [{'collection': {'$nin': ['bravo']}}]}]}, {'alpha', 'bravo'}),
    ],
)
def test_get_referenced_slugs(query, expected):
    assert get_referenced_slugs(query) == expected


def test_get_referenced_slugs_invalid_filter():
    with pytest.raises(SaltBoxValidationException):
        get_referenced_slugs({'$and': [{'collection': 'alpha'}]})


@pytest.mark.parametrize(
    ('edges', 'expected'),
    [
        ({}, None),
        ({'a': ['b'], 'b': ['c']}, None),
        ({'a': ['a']}, ['a', 'a']),
        ({'a': ['b'], 'b': ['c'], 'c': ['a']}, ['a', 'b', 'c', 'a']),
        ({'a': ['b'], 'b': ['c'], 'c': ['b']}, None),
        ({'a': ['x', 'b'], 'x': ['y'], 'b': ['a']}, ['a', 'b', 'a']),
    ],
)
def test_find_cycle(edges, expected):
    assert find_cycle('a', edges) == expected


# Create / update


@pytest.mark.asyncio
async def test_create_with_unknown_reference(create):
    await create('alpha')

    with pytest.raises(UnknownCollectionReferenceException) as exc_info:
        await create('bravo', {'$or': [_in('alpha', 'missing'), _in('lost')]})

    assert exc_info.value.slugs == ['lost', 'missing']


@pytest.mark.asyncio
async def test_create_with_existing_reference(service, create):
    await create('alpha')
    bravo_id = await create('bravo', _in('alpha'))

    assert (await service.get(bravo_id)).query == _in('alpha')


@pytest.mark.asyncio
async def test_update_with_unknown_reference(service, create):
    await create('alpha')

    with pytest.raises(UnknownCollectionReferenceException):
        await _update_query(service, 'alpha', _in('missing'))


@pytest.mark.asyncio
async def test_update_with_self_reference(service, create):
    await create('alpha')

    with pytest.raises(CyclicCollectionReferenceException) as exc_info:
        await _update_query(service, 'alpha', _in('alpha'))

    assert exc_info.value.slugs == ['alpha', 'alpha']


@pytest.mark.asyncio
async def test_update_with_mutual_reference(service, create):
    await create('alpha')
    await create('bravo', _in('alpha'))

    with pytest.raises(CyclicCollectionReferenceException) as exc_info:
        await _update_query(service, 'alpha', _in('bravo'))

    assert exc_info.value.slugs == ['alpha', 'bravo', 'alpha']


@pytest.mark.asyncio
async def test_update_with_reference_to_descendant(service, create):
    alpha_id = await create('alpha')
    await create('child', parent_id=alpha_id)

    with pytest.raises(CyclicCollectionReferenceException) as exc_info:
        await _update_query(service, 'alpha', _in('child'))

    assert exc_info.value.slugs == ['alpha', 'child', 'alpha']


@pytest.mark.asyncio
async def test_update_parent_to_referencing_collection(service, create):
    await create('alpha')
    await create('xray', _in('alpha'))

    with pytest.raises(CyclicCollectionReferenceException) as exc_info:
        await service.update_by_slug('alpha', CollectionUpdateSchema(title='alpha', parent_slug='xray'))

    assert exc_info.value.slugs == ['alpha', 'xray', 'alpha']


@pytest.mark.asyncio
async def test_update_with_valid_references(service, create):
    alpha_id = await create('alpha')
    await create('child', parent_id=alpha_id)
    await create('bravo', _in('alpha'))

    collection = await _update_query(service, 'child', _in('bravo'))

    assert collection.query == _in('bravo')


# Move


@pytest.mark.asyncio
async def test_move_under_referencing_collection(service, create):
    alpha_id = await create('alpha')
    xray_id = await create('xray', _in('alpha'))

    with pytest.raises(CyclicCollectionReferenceException) as exc_info:
        await service.move(target_id=alpha_id, parent_id=xray_id)

    assert exc_info.value.slugs == ['alpha', 'xray', 'alpha']
    assert (await service.get(alpha_id)).parent_slug == 'root'


@pytest.mark.asyncio
async def test_move_into_own_descendant(service, create):
    alpha_id = await create('alpha')
    child_id = await create('child', parent_id=alpha_id)

    with pytest.raises(SaltBoxValidationException, match='own descendant'):
        await service.move(target_id=alpha_id, parent_id=child_id)


@pytest.mark.asyncio
async def test_move_with_valid_references(service, create):
    alpha_id = await create('alpha')
    bravo_id = await create('bravo', _in('alpha'))

    await service.move(target_id=bravo_id, parent_id=alpha_id)

    assert (await service.get(bravo_id)).parent_slug == 'alpha'


# Delete


@pytest.mark.asyncio
async def test_delete_referenced_collection(service, create):
    alpha_id = await create('alpha')
    await create('bravo', _in('alpha'))
    await create('xray', {'collection': {'$nin': ['alpha']}})

    with pytest.raises(ReferencedCollectionDeleteException) as exc_info:
        await service.delete_by_slug('alpha')

    assert exc_info.value.slugs == ['bravo', 'xray']
    assert await service.exists({'_id': alpha_id})


@pytest.mark.asyncio
async def test_delete_collection_with_referenced_descendant(service, create):
    alpha_id = await create('alpha')
    await create('child', parent_id=alpha_id)
    await create('bravo', _in('child'))

    with pytest.raises(ReferencedCollectionDeleteException) as exc_info:
        await service.delete_by_slug('alpha')

    assert exc_info.value.slugs == ['bravo']


@pytest.mark.asyncio
async def test_delete_subtree_with_internal_references(service, create):
    alpha_id = await create('alpha')
    child_id = await create('child', parent_id=alpha_id)
    sibling_id = await create('sibling', _in('child'), parent_id=alpha_id)
    bravo_id = await create('bravo')

    assert await service.delete_by_slug('alpha') == 3

    for collection_id in (alpha_id, child_id, sibling_id):
        assert not await service.exists({'_id': collection_id})
    assert await service.exists({'_id': bravo_id})
