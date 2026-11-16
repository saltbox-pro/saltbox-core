from unittest.mock import AsyncMock, Mock, patch

import pytest
from taskiq.scheduler.scheduled_task import ScheduledTask

from saltbox_sdk.utilities.taskiq import SaltboxTaskiqScheduler, TaskAlreadyRunningException


@pytest.mark.asyncio
async def test_busy_schedule_is_not_marked_as_sent() -> None:
    source = Mock(pre_send=AsyncMock(), post_send=AsyncMock())
    scheduler = SaltboxTaskiqScheduler(Mock(), [source])
    task = ScheduledTask(task_name='test', labels={}, args=[], kwargs={}, schedule_id='schedule', cron='* * * * *')
    with patch('taskiq.scheduler.scheduler.AsyncKicker.kiq', new_callable=AsyncMock) as send:
        send.side_effect = [TaskAlreadyRunningException(), None]
        await scheduler.on_ready(source, task)
        source.post_send.assert_not_awaited()
        await scheduler.on_ready(source, task)
    assert send.await_count == 2
    source.post_send.assert_awaited_once_with(task)


@pytest.mark.asyncio
async def test_scheduler_does_not_hide_publication_errors() -> None:
    source = Mock(pre_send=AsyncMock(), post_send=AsyncMock())
    scheduler = SaltboxTaskiqScheduler(Mock(), [source])
    task = ScheduledTask(task_name='test', labels={}, args=[], kwargs={}, schedule_id='schedule', cron='* * * * *')
    with patch('taskiq.scheduler.scheduler.AsyncKicker.kiq', new_callable=AsyncMock) as send:
        send.side_effect = ConnectionError('publication failed')
        with pytest.raises(ConnectionError, match='publication failed'):
            await scheduler.on_ready(source, task)
    source.post_send.assert_not_awaited()
