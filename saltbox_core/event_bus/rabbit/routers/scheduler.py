from anyio import Path
from faststream.rabbit import RabbitRouter
from faststream.rabbit.annotations import ContextRepo

from saltbox_core.event_bus.rabbit.exchanges import exchanges
from saltbox_core.scheduler.handlers import scheduler_handlers
from saltbox_sdk.scheduler.handler import run_scheduled_task, sync_scheduler_templates
from saltbox_sdk.scheduler.messages import RunTaskEventBusMessage, SyncTemplatesRequestEventBusMessage

router = RabbitRouter(prefix='scheduler_')


@router.subscriber('sync_templates.core', exchange=exchanges['scheduler_sync_templates'])
async def sync_templates(message: SyncTemplatesRequestEventBusMessage) -> None:
    if message.target is not None and message.target not in ['core', '*']:
        return

    await sync_scheduler_templates(
        templates_path=Path(__file__).parent.parent.parent.parent.joinpath('scheduler/templates'),
        default_target='core',
    )


@router.subscriber('run_task.core', exchange=exchanges['scheduler_run_task'])
async def run_task(message: RunTaskEventBusMessage, context: ContextRepo) -> None:
    if message.target is not None and message.target not in ['core', '*']:
        return

    await run_scheduled_task(message=message, context=context, scheduler_handlers=scheduler_handlers)
