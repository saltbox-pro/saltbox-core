from datetime import UTC, datetime

import pytest

from saltbox_core.jobs.jobs_watcher import JobsWatcher
from saltbox_core.jobs.schemas.job_schemas import JobSimpleWithSourceSchema, JobStatus
from saltbox_sdk.db.mongo.schemas_base import PyObjectId

pytestmark = pytest.mark.asyncio


def _job(jid, source_type, status=JobStatus.starting):
    return JobSimpleWithSourceSchema.model_validate(
        {
            '_id': PyObjectId(),
            'jid': jid,
            'salt_master': 'salt',
            'status': status,
            'source': {'type': source_type, 'id': 'source-id'},
        }
    )


@pytest.fixture
def watcher(mocker):
    watcher = object.__new__(JobsWatcher)
    watcher.job_service = mocker.MagicMock()
    watcher.job_service.get_list = mocker.AsyncMock()
    watcher.job_service.bulk_update = mocker.AsyncMock()
    watcher.job_return_service = mocker.MagicMock()
    watcher.job_return_service.get_list = mocker.AsyncMock(return_value=[])
    watcher.finish_completed_jobs = mocker.AsyncMock()

    return watcher


async def test_expired_jobs_are_selected_once_and_split_by_status(watcher, mocker):
    mocker.patch('saltbox_core.jobs.jobs_watcher.process_task_job_error.kiq', mocker.AsyncMock())
    starting_job = _job('20261103120000000001', 'system')
    running_job = _job('20261103120000000002', 'system', status=JobStatus.running)
    watcher.job_service.get_list.return_value = [starting_job, running_job]
    watcher.job_service.bulk_update.return_value = [starting_job.id]
    now = datetime(2026, 11, 3, 12, tzinfo=UTC)

    await watcher.process_expired_jobs(now)

    watcher.job_service.get_list.assert_awaited_once_with(
        query={'status': {'$in': [JobStatus.starting, JobStatus.running]}, 'waiting_expires_at_dt': {'$lt': now}},
        projection_model=JobSimpleWithSourceSchema,
    )
    watcher.job_service.bulk_update.assert_awaited_once_with(
        query={'_id': {'$in': [starting_job.id]}, 'status': JobStatus.starting},
        data={'status': JobStatus.launch_error, 'launch_error_type': 'expired'},
    )
    watcher.finish_completed_jobs.assert_awaited_once_with({running_job.id})


async def test_expired_starting_jobs_become_launch_errors(watcher, mocker):
    kiq = mocker.patch('saltbox_core.jobs.jobs_watcher.process_task_job_error.kiq', mocker.AsyncMock())
    task_job = _job('20261103120000000001', 'task')
    system_job = _job('20261103120000000002', 'system')
    started_meanwhile_job = _job('20261103120000000003', 'task')
    watcher.job_service.bulk_update.return_value = [task_job.id, system_job.id]

    await watcher._process_expired_starting_jobs([task_job, system_job, started_meanwhile_job])

    kiq.assert_awaited_once_with(jid=task_job.jid, salt_master='salt')


async def test_starting_jobs_not_removed_from_queue_are_kept(watcher, mocker):
    mocker.patch.object(watcher, '_remove_from_create_queue', mocker.AsyncMock(return_value=False))

    await watcher._process_expired_starting_jobs([_job('20261103120000000001', 'task')])

    watcher.job_service.bulk_update.assert_not_awaited()
