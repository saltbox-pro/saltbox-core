from datetime import UTC, datetime

import pytest
from bson import ObjectId

from saltbox_core.tasks.repositories.tasks_minion import TaskMinionRepository
from saltbox_core.tasks.schemas.tasks_minion import TaskMinionExportSchema, TaskMinionStatus
from saltbox_core.tasks.services.tasks_minion import TaskMinionService
from saltbox_sdk.db.mongo.schemas_base import SortOrder


@pytest.mark.asyncio
async def test_iter_export_rows(mocked_db, mocker):
    mocker.patch('saltbox_core.tasks.services.tasks_minion.get_mongo_db', return_value=mocked_db)
    task_minion_service = TaskMinionService(repo=TaskMinionRepository(mocked_db), rdb=mocker.MagicMock())

    started = datetime(2026, 10, 12, 10, 0, tzinfo=UTC)
    finished = datetime(2026, 10, 12, 10, 5, tzinfo=UTC)
    task_minions = [
        TaskMinionExportSchema(
            minion_id='m2',
            master='master2',
            status=TaskMinionStatus.failed,
            count_runs=2,
            start_last_dt=started,
            finished_dt=finished,
        ),
        TaskMinionExportSchema(minion_id='m1', master='master1', count_runs=0),
    ]

    async def iter_list(*args, **kwargs):
        for task_minion in task_minions:
            yield task_minion

    mocked_iter_list = mocker.patch.object(task_minion_service, 'iter_list', side_effect=iter_list)

    query = {'task_id': ObjectId()}
    sort = {'start_last_dt': SortOrder.DESC}
    rows = [row async for row in task_minion_service.iter_export_rows(query, sort=sort)]

    mocked_iter_list.assert_called_once_with(query, sort=sort, projection_model=TaskMinionExportSchema)
    assert rows == [
        {
            'minion_id': 'm2',
            'master': 'master2',
            'status': TaskMinionStatus.failed,
            'count_runs': 2,
            'start_last_dt': started,
            'finished_dt': finished,
        },
        {
            'minion_id': 'm1',
            'master': 'master1',
            'status': TaskMinionStatus.pending,
            'count_runs': 0,
            'start_last_dt': None,
            'finished_dt': None,
        },
    ]
