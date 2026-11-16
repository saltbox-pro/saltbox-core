from datetime import timedelta
from unittest.mock import AsyncMock, Mock

import pytest
from redis.exceptions import ConnectionError

from saltbox_core.minion_collections.schemas.collection_membership_run import (
    CollectionMembershipRun,
    CollectionSynchronizationModel,
)
from saltbox_core.minion_collections.services.collection_membership import CollectionMembershipService
from saltbox_core.minion_collections.utils.membership_schedule import get_activity_collection_ids, should_synchronize
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.utilities.helpers import utc_now


def history(statuses):
    now = utc_now()
    return [CollectionMembershipRun(status=status, started_at=now + timedelta(seconds=i), data=data)
            for i, (status, data) in enumerate(statuses)]


@pytest.mark.parametrize('skips,expected', [(0, False), (1, False), (3, False), (4, True), (5, True)])
def test_every_fifth_iteration(skips, expected):
    runs = history([('succeeded', {})] + [('skipped', {'reason': 'iteration_policy'})] * skips)
    assert should_synchronize(runs, 5) is expected


def test_missing_success_failure_and_busy_skips():
    assert should_synchronize([], 5)
    assert should_synchronize(history([('skipped', {'reason': 'iteration_policy'})] * 4), 5)
    assert should_synchronize(history([('succeeded', {}), ('failed', {})]), 5)
    assert should_synchronize(history([('succeeded', {}), ('started', {})]), 5)
    assert not should_synchronize(history([('succeeded', {})] +
        [('skipped', {'reason': 'already_queued_or_running'})] * 5), 5)
    assert should_synchronize(history([('succeeded', {})]), 1)
    assert not should_synchronize(history([('succeeded', {})] +
        [('skipped', {'reason': 'iteration_policy'})] * 4 + [('succeeded', {})]), 5)


@pytest.mark.parametrize('field', ['last_activity', 'last_activity_seconds', 'is_not_active', 'is_never_active'])
def test_activity_propagates_through_parent_and_negative_reference(field):
    root_id, child_id, reference_id, static_id = [PyObjectId() for _ in range(4)]
    nodes = [
        CollectionSynchronizationModel(_id=root_id, slug='root', query={'$or': [{field: True}]}),
        CollectionSynchronizationModel(_id=child_id, slug='child', parent_id=root_id),
        CollectionSynchronizationModel(_id=reference_id, slug='ref', query={'collection': {'$nin': ['child']}}),
        CollectionSynchronizationModel(_id=static_id, slug='static', query={'grains.os': 'ALT'}),
    ]
    assert get_activity_collection_ids(nodes) == {root_id, child_id, reference_id}


@pytest.mark.asyncio
async def test_plan_skips_static_but_keeps_activity_and_deleted():
    static_id, active_id, deleted_id = [PyObjectId() for _ in range(3)]
    nodes = [CollectionSynchronizationModel(_id=static_id, slug='static'),
             CollectionSynchronizationModel(_id=active_id, slug='active', query={'is_not_active': True})]
    runs = Mock(get_lists=AsyncMock(return_value={static_id: history([('succeeded', {})])}))
    service = CollectionMembershipService(
        Mock(get_active_collection_ids=AsyncMock(return_value=[deleted_id])),
        Mock(get_list=AsyncMock(return_value=nodes)), Mock(), runs,
    )
    assert await service.get_collection_synchronization_plan() == {
        static_id: False, active_id: True, deleted_id: True,
    }
    runs.get_lists.assert_awaited_once_with([static_id])
    runs.get_lists.side_effect = ConnectionError('offline')
    assert all((await service.get_collection_synchronization_plan()).values())
