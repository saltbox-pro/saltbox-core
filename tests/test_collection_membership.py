from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest
from pymongo import AsyncMongoClient

from saltbox_core.minion_collections.repositories.collection_membership import CollectionMembershipRepository
from saltbox_core.minion_collections.schemas.collection_membership_run import CollectionSynchronizationBranch
from saltbox_core.minion_collections.services.collection_membership import CollectionMembershipService
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.exceptions import ObjectNotFoundException
from saltbox_sdk.utilities.helpers import utc_now


@pytest.mark.asyncio
async def test_membership_intervals_and_noop(mocked_db: Any) -> None:
    repo = CollectionMembershipRepository(mocked_db)
    repo.collection.with_options = Mock(return_value=repo.collection)
    service = CollectionMembershipService(repo, Mock(), Mock(), Mock(save=AsyncMock()))
    collection_id, minion_id = PyObjectId(), PyObjectId()
    renew = AsyncMock(return_value=True)
    start = utc_now()
    await service.apply_membership(collection_id, {minion_id}, start, renew)
    await service.apply_membership(collection_id, {minion_id}, start + timedelta(seconds=1), renew)
    assert await repo.collection.count_documents({}) == 1
    await service.apply_membership(collection_id, set(), start + timedelta(seconds=2), renew)
    assert await repo.get_active_minion_ids(collection_id) == set()
    await service.apply_membership(collection_id, {minion_id}, start + timedelta(seconds=3), renew)
    docs = await repo.collection.find({}).to_list()
    assert len(docs) == 2
    closed = next(doc for doc in docs if doc['exited_at'] is not None)
    active = next(doc for doc in docs if doc['exited_at'] is None)
    assert closed['_id'] != active['_id']
    assert closed['entered_at'] == docs[0]['entered_at']
    assert active['entered_at'] > closed['exited_at']


@pytest.mark.asyncio
async def test_lost_lock_prevents_writes(mocked_db: Any) -> None:
    repo = CollectionMembershipRepository(mocked_db)
    service = CollectionMembershipService(repo, Mock(), Mock(), Mock(save=AsyncMock()))
    with pytest.raises(RuntimeError, match='lock was lost'):
        await service.apply_membership(PyObjectId(), {PyObjectId()}, utc_now(), AsyncMock(return_value=False))
    assert await repo.collection.count_documents({}) == 0


@pytest.mark.asyncio
async def test_dispatch_ids_include_deleted_collections() -> None:
    existing_id, deleted_id = PyObjectId(), PyObjectId()
    repo = Mock(get_active_collection_ids=AsyncMock(return_value=[existing_id, deleted_id]))
    collections = Mock(
        get_list=AsyncMock(return_value=[Mock(id=existing_id, slug='existing', parent_id=None, query={})])
    )
    service = CollectionMembershipService(
        repo, collections, Mock(), Mock(save=AsyncMock(), get_lists=AsyncMock(return_value={}))
    )
    assert await service.get_collection_synchronization_plan() == {existing_id: True, deleted_id: True}


@pytest.mark.asyncio
@pytest.mark.parametrize('deleted', [False, True])
async def test_synchronize_reads_current_collection(deleted: bool) -> None:
    collection_id, minion_id = PyObjectId(), PyObjectId()
    query = {'$and': [{'grains.os': 'ALT'}, {'master': 'master1'}]}
    collections = Mock(get=AsyncMock(return_value=Mock(full_query=query)))
    if deleted:
        collections.get.side_effect = ObjectNotFoundException()
    minions = Mock(get_ids=AsyncMock(return_value=[minion_id]))
    service = CollectionMembershipService(Mock(), collections, minions, Mock(save=AsyncMock()))
    renew = AsyncMock(return_value=True)
    with patch.object(service, 'apply_membership', new_callable=AsyncMock) as apply_membership:
        result = await service.synchronize_collection(collection_id, renew)
    assert result == (None if deleted else {minion_id})
    assert apply_membership.await_args is not None
    assert apply_membership.await_args.args[:2] == (collection_id, set() if deleted else {minion_id})
    if deleted:
        minions.get_ids.assert_not_awaited()
    else:
        minions.get_ids.assert_awaited_once_with(query)


@pytest.mark.asyncio
async def test_dispatcher_skips_busy_collections() -> None:
    from saltbox_core.minion_collections.tiq_tasks import (
        synchronize_collection_membership,
        synchronize_collection_memberships,
    )
    from saltbox_sdk.utilities.taskiq import TaskAlreadyRunningException

    ids = [PyObjectId(), PyObjectId()]
    service = Mock(
        get_collection_synchronization_plan=AsyncMock(return_value=dict.fromkeys(ids, True)),
        get_synchronization_branches=AsyncMock(
            return_value=[CollectionSynchronizationBranch(collection_id=str(i)) for i in ids]
        ),
        record_skipped_run=AsyncMock(),
    )
    lock = Mock(renew_execution_lock=AsyncMock(return_value=True))
    with patch(
        'saltbox_core.minion_collections.tiq_tasks.synchronize_collection_membership.kiq', new_callable=AsyncMock
    ) as send:
        send.side_effect = [TaskAlreadyRunningException(), None]
        await synchronize_collection_memberships.original_func(service=service, unique_lock=lock)
    service.record_skipped_run.assert_awaited_once_with(ids[0], 'already_queued_or_running')
    assert send.await_count == 2
    assert [call.args[0] for call in send.await_args_list] == list(map(str, ids))
    assert synchronize_collection_membership.labels['queue_name'] == 'queue-membership'
    assert synchronize_collection_membership.labels['unique_kwargs'] == ['collection_id']
    assert synchronize_collection_memberships.labels['queue_name'] == 'queue-membership'


@pytest.mark.asyncio
@pytest.mark.parametrize('parent_size,moved', [(0, False), (2, False), (3, False), (0, True)])
async def test_parent_result_limits_search(parent_size, moved):
    from saltbox_core.config import SETTINGS

    collection_id, parent_id = PyObjectId(), PyObjectId()
    parent_ids = {PyObjectId() for _ in range(parent_size)}
    own_query, full_query = {'master': 'm1'}, {'grains.os': 'ALT'}
    collection = Mock(parent_id=PyObjectId() if moved else parent_id, query=own_query, full_query=full_query)
    minions = Mock(get_ids=AsyncMock(return_value=[]))
    service = CollectionMembershipService(
        Mock(), Mock(get=AsyncMock(return_value=collection)), minions, Mock(save=AsyncMock())
    )
    with (
        patch.object(SETTINGS, 'membership_parent_ids_limit', 2),
        patch.object(service, 'apply_membership', new_callable=AsyncMock) as apply,
    ):
        result = await service.synchronize_collection(
            collection_id, AsyncMock(return_value=True), parent_id, parent_ids
        )
    assert result == set()
    apply.assert_awaited_once()
    assert apply.await_args.args[:2] == (collection_id, set())
    if moved or parent_size > 2:
        minions.get_ids.assert_awaited_once_with(full_query)
    elif parent_size:
        query = minions.get_ids.await_args.args[0]
        assert set(query['$and'][0]['_id']['$in']) == parent_ids
        assert query['$and'][1] == own_query
    else:
        minions.get_ids.assert_not_awaited()


@pytest.mark.asyncio
async def test_branches_split_at_skipped_parent():
    root, skipped, child, deleted = [PyObjectId() for _ in range(4)]
    service = CollectionMembershipService(
        Mock(),
        Mock(
            get_list=AsyncMock(
                return_value=[
                    Mock(id=root, parent_id=None),
                    Mock(id=skipped, parent_id=root),
                    Mock(id=child, parent_id=skipped),
                ]
            )
        ),
        Mock(),
        Mock(),
    )
    branches = await service.get_synchronization_branches({root: True, skipped: False, child: True, deleted: True})
    assert {b.collection_id for b in branches} == {str(root), str(child), str(deleted)}
    assert all(not b.children for b in branches)
    branches = await service.get_synchronization_branches({root: True, skipped: True, child: True})
    assert len(branches) == 1
    assert branches[0].children[0].children[0].collection_id == str(child)


@pytest.mark.asyncio
@pytest.mark.parametrize('failed', [False, True])
async def test_children_enqueued_after_parent_write(failed):
    from saltbox_core.minion_collections.tiq_tasks import synchronize_collection_membership

    root, child, minion = [PyObjectId() for _ in range(3)]
    service = Mock(synchronize_collection=AsyncMock(return_value={minion}))
    if failed:
        service.synchronize_collection.side_effect = RuntimeError('failed')

    async def check_send(*args, **kwargs):
        service.synchronize_collection.assert_awaited_once()
        assert kwargs['parent_minion_ids'] == (None if failed else [str(minion)])
        assert kwargs['parent_id'] == str(root)

    with patch(
        'saltbox_core.minion_collections.tiq_tasks.synchronize_collection_membership.kiq', new_callable=AsyncMock
    ) as send:
        send.side_effect = check_send
        call = synchronize_collection_membership.original_func(
            str(root),
            children=[{'collection_id': str(child)}],
            service=service,
            unique_lock=Mock(renew_execution_lock=AsyncMock(return_value=True)),
        )
        if failed:
            with pytest.raises(RuntimeError, match='failed'):
                await call
        else:
            await call
        send.assert_awaited_once()


@pytest.mark.asyncio
async def test_busy_parent_does_not_drop_children():
    from saltbox_core.minion_collections.tiq_tasks import enqueue_membership_branch
    from saltbox_sdk.utilities.taskiq import TaskAlreadyRunningException

    root, child = PyObjectId(), PyObjectId()
    service = Mock(record_skipped_run=AsyncMock())
    branch = CollectionSynchronizationBranch(
        collection_id=str(root), children=[CollectionSynchronizationBranch(collection_id=str(child))]
    )
    with patch(
        'saltbox_core.minion_collections.tiq_tasks.synchronize_collection_membership.kiq', new_callable=AsyncMock
    ) as send:
        send.side_effect = [TaskAlreadyRunningException(), None]
        await enqueue_membership_branch(branch, service)
        assert send.await_count == 2
        assert send.await_args.kwargs['parent_minion_ids'] is None
        assert send.await_args.args[0] == str(child)


@pytest.mark.asyncio
async def test_large_result_is_written_but_not_passed_to_children():
    from saltbox_core.config import SETTINGS

    ids = {PyObjectId(), PyObjectId()}
    service = CollectionMembershipService(
        Mock(),
        Mock(get=AsyncMock(return_value=Mock(full_query={}))),
        Mock(get_ids=AsyncMock(return_value=list(ids))),
        Mock(save=AsyncMock()),
    )
    with (
        patch.object(SETTINGS, 'membership_parent_ids_limit', 1),
        patch.object(service, 'apply_membership', new_callable=AsyncMock) as apply,
    ):
        result = await service.synchronize_collection(PyObjectId(), AsyncMock(return_value=True))
    assert result is None
    assert apply.await_args.args[1] == ids


@pytest.mark.asyncio
async def test_inherited_bulk_create_uses_transaction_write_concern() -> None:
    client = AsyncMongoClient(connect=False)
    repo = CollectionMembershipRepository(client.test_db)
    session = Mock(in_transaction=True)
    document = {'collection_id': PyObjectId(), 'minion_inner_id': PyObjectId(), 'entered_at': utc_now()}
    try:
        with patch('pymongo.asynchronous.bulk._AsyncBulk.execute', new_callable=AsyncMock) as execute:
            ids = await repo.bulk_create([document], session=session)
        assert len(ids) == 1
        write_concern, passed_session, _ = execute.await_args.args
        assert write_concern.acknowledged
        assert passed_session is session
    finally:
        await client.close()
