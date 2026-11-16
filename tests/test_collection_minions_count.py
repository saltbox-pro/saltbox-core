from datetime import datetime, UTC

import pytest

from saltbox_core.minion_collections.repositories.collection import CollectionRepository
from saltbox_core.minion_collections.schemas.collection import CollectionBaseTreeModel, CollectionTreeNodeSchema
from saltbox_sdk.db.mongo.schemas_base import PyObjectId


@pytest.mark.asyncio
async def test_cached_minions_count(mocked_db):
    repo = CollectionRepository(mocked_db)
    root = await repo.create({'title': 'Root', 'slug': 'root', 'query': {}})
    child = await repo.create({'title': 'Child', 'slug': 'child', 'query': {}, 'parent_id': root})
    empty = await repo.create({'title': 'Empty', 'slug': 'empty', 'query': {}})
    minion = PyObjectId()
    await mocked_db['minion_collection_memberships'].insert_many([
        {'collection_id': root, 'minion_inner_id': minion, 'exited_at': datetime.now(UTC)},
        {'collection_id': root, 'minion_inner_id': minion, 'exited_at': None},
        {'collection_id': root, 'minion_inner_id': PyObjectId(), 'exited_at': None},
        {'collection_id': child, 'minion_inner_id': minion, 'exited_at': None},
        {'collection_id': empty, 'minion_inner_id': minion, 'exited_at': datetime.now(UTC)},
    ])
    assert (await repo.get(root)).minions_count == 2
    assert (await repo.get(empty)).minions_count == 0
    expected = {root: 2, child: 1, empty: 0}
    assert {item.id: item.minions_count for item in await repo.get_list()} == expected
    assert {item['_id']: item['minions_count'] for item in await repo.get_flat_list()} == expected
    tree = await repo.get_tree(projection_model=CollectionTreeNodeSchema)
    root_node = next(item for item in tree if item.id == root)
    assert root_node.minions_count == 2
    assert root_node.children[0].minions_count == 1
    assert await repo.prepare_pipeline(dict.fromkeys(CollectionBaseTreeModel.model_fields, 1)) == []
    filtered = await repo.get_list(query={'minions_count': {'$gt': 0}}, sort={'minions_count': -1})
    assert [item.minions_count for item in filtered] == [2, 1]
