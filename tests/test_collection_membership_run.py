from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from redis.exceptions import ConnectionError

from saltbox_core.config import SETTINGS
from saltbox_core.minion_collections.repositories.collection_membership_run import CollectionMembershipRunRepository
from saltbox_core.minion_collections.schemas.collection_membership_run import CollectionMembershipRun
from saltbox_core.minion_collections.services.collection_membership import CollectionMembershipService
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.utilities.helpers import utc_now


@pytest.mark.asyncio
@pytest.mark.parametrize('ttl', [21600, 3600])
async def test_run_update_keeps_original_expiration_and_other_runs(ttl, monkeypatch) -> None:
    monkeypatch.setattr(SETTINGS, 'membership_run_history_ttl', ttl)
    pipe = MagicMock()
    pipe.execute = AsyncMock()
    pipe.__aenter__ = AsyncMock(return_value=pipe)
    rdb = Mock(pipeline=Mock(return_value=pipe))
    repo = CollectionMembershipRunRepository(rdb)
    collection_id = PyObjectId()
    run = CollectionMembershipRun()
    await repo.save(collection_id, run)
    first_expiration = pipe.execute_command.call_args
    first_field = pipe.hset.call_args.args[1]
    run.status = 'succeeded'
    run.finished_at = utc_now()
    await repo.save(collection_id, run)
    assert pipe.execute_command.call_args == first_expiration
    assert pipe.hset.call_args.args[1] == first_field
    assert first_expiration.args[2] == int(run.started_at.timestamp() * 1000) + ttl * 1000
    await repo.save(collection_id, CollectionMembershipRun(status='skipped'))
    assert pipe.hset.call_args.args[1] != first_field
    rdb.pipeline.assert_called_with(transaction=True)


@pytest.mark.asyncio
async def test_history_reads_json_bytes_and_orders_runs() -> None:
    older = CollectionMembershipRun()
    newer = CollectionMembershipRun()
    repo = CollectionMembershipRunRepository(
        Mock(hvals=AsyncMock(return_value=[newer.model_dump_json().encode(), older.model_dump_json()]))
    )
    assert await repo.get_list(PyObjectId()) == [older, newer]


@pytest.mark.asyncio
@pytest.mark.parametrize('fails', [False, True])
async def test_history_records_commit_outcome(fails: bool) -> None:
    saved = []

    async def save(collection_id, run):
        saved.append(run.model_copy(deep=True))

    service = CollectionMembershipService(
        Mock(),
        Mock(get=AsyncMock(return_value=Mock(full_query={}))),
        Mock(get_ids=AsyncMock(return_value=[PyObjectId()])),
        Mock(save=AsyncMock(side_effect=save)),
    )
    error = RuntimeError('commit failed')
    with patch.object(service, 'apply_membership', new_callable=AsyncMock) as apply:
        if fails:
            apply.side_effect = error
            with pytest.raises(RuntimeError, match='commit failed') as caught:
                await service.synchronize_collection(PyObjectId(), AsyncMock(return_value=True))
            assert caught.value is error
        else:
            await service.synchronize_collection(PyObjectId(), AsyncMock(return_value=True))
    assert [run.status for run in saved] == ['started', 'failed' if fails else 'succeeded']
    assert saved[0].id == saved[1].id
    assert saved[0].started_at == saved[1].started_at
    assert saved[0].finished_at is None
    assert saved[1].finished_at is not None
    assert saved[1].data['duration_ms'] >= 0
    if fails:
        assert saved[1].data['error'] == 'commit failed'
    else:
        assert saved[1].data['minion_count'] == 1


@pytest.mark.asyncio
async def test_redis_failure_does_not_fail_successful_membership() -> None:
    service = CollectionMembershipService(
        Mock(),
        Mock(get=AsyncMock(return_value=Mock(full_query={}))),
        Mock(get_ids=AsyncMock(return_value=[])),
        Mock(save=AsyncMock(side_effect=ConnectionError('offline'))),
    )
    with patch.object(service, 'apply_membership', new_callable=AsyncMock) as apply:
        await service.synchronize_collection(PyObjectId(), AsyncMock(return_value=True))
    apply.assert_awaited_once()


@pytest.mark.asyncio
async def test_skip_has_its_own_history_record() -> None:
    repo = Mock(save=AsyncMock())
    service = CollectionMembershipService(Mock(), Mock(), Mock(), repo)
    collection_id = PyObjectId()
    await service.record_skipped_run(collection_id, 'already_queued_or_running')
    recorded_id, run = repo.save.await_args.args
    assert recorded_id == collection_id
    assert run.status == 'skipped'
    assert run.data == {'reason': 'already_queued_or_running'}
    assert run.started_at == run.finished_at
