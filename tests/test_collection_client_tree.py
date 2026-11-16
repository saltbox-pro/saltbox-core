from datetime import UTC, datetime

import pytest

from saltbox_core.minion_collections.repositories.collection import CollectionRepository
from saltbox_core.minion_collections.repositories.collection_membership import CollectionMembershipRepository
from saltbox_core.minion_collections.services.collection import CollectionService
from saltbox_sdk.db.mongo.schemas_base import PyObjectId


@pytest.mark.asyncio
async def test_client_tree_availability(mocked_db):
    repo = CollectionRepository(mocked_db)
    service = CollectionService(repo)
    root = await repo.create({'title': 'Root', 'slug': 'root'})
    parent = await repo.create({'title': 'Parent', 'slug': 'parent', 'parent_id': root})
    leaf = await repo.create({'title': 'Leaf', 'slug': 'leaf', 'parent_id': parent})
    other = await repo.create({'title': 'Other', 'slug': 'other', 'parent_id': root})
    minion = PyObjectId()
    await mocked_db['minion_collection_memberships'].insert_many(
        [
            {'collection_id': leaf, 'minion_inner_id': minion, 'exited_at': None},
            {'collection_id': other, 'minion_inner_id': minion, 'exited_at': datetime.now(UTC)},
            {'collection_id': other, 'minion_inner_id': PyObjectId(), 'exited_at': None},
        ]
    )
    memberships = CollectionMembershipRepository(mocked_db)
    ids = await memberships.get_minion_collection_ids(minion)
    assert ids == [leaf]
    opa = {'_id': parent}
    tree = await service.get_available_tree(opa, only_available=False, collection_ids=ids)
    assert len(tree) == 1
    assert tree[0].id == root
    assert tree[0].is_available is False
    assert [node.id for node in tree[0].children] == [parent]
    branch = tree[0].children[0]
    assert branch.is_available is True
    assert [node.id for node in branch.children] == [leaf]
    assert branch.children[0].is_available is False
    assert branch.children[0].minions_count == 1
    filtered = await service.get_available_tree(opa, collection_ids=ids)
    assert [node.id for node in filtered] == [parent]
    assert filtered[0].is_available is True
    assert filtered[0].children == []
    assert await service.get_available_tree({}, collection_ids=[]) == []
    assert await memberships.get_minion_collection_ids(PyObjectId()) == []
    assert await service.get_available_tree({'_id': PyObjectId()}) == []
    full = await service.get_available_tree(opa, only_available=False)
    assert {node.id for node in full[0].children} == {parent, other}
    unrestricted = await service.get_available_tree({})
    assert unrestricted[0].is_available is True
    assert all(node.is_available for node in unrestricted[0].children)
