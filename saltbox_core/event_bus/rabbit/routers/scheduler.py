from faststream.rabbit import RabbitRouter
from faststream.rabbit.annotations import ContextRepo

from saltbox_core.event_bus.rabbit.exchanges import exchanges
from saltbox_core.scheduler.handlers.run_job import run_job_handler
from saltbox_core.scheduler.handlers.run_task import run_task_handler
from saltbox_core.scheduler.utils import sync_templates as _sync_templates
from saltbox_sdk.scheduler.handler import run_scheduled_task
from saltbox_sdk.scheduler.messages import RunTaskEventBusMessage, SyncTemplatesRequestEventBusMessage

router = RabbitRouter(prefix='scheduler_')


@router.subscriber('sync_templates.core', exchange=exchanges['scheduler_sync_templates'])
async def sync_templates(message: SyncTemplatesRequestEventBusMessage) -> None:
    if message.target is not None and message.target not in ['core', '*']:
        return
    await _sync_templates()


@router.subscriber('run_task.core', exchange=exchanges['scheduler_run_task'])
async def run_task(message: RunTaskEventBusMessage, context: ContextRepo) -> None:
    if message.target is not None and message.target not in ['core', '*']:
        return

    await run_scheduled_task(
        message=message,
        context=context,
        scheduler_handlers={
            'run_task': run_task_handler,
            'run_job': run_job_handler,
        },
    )
