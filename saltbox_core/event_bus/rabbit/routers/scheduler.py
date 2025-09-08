from faststream.rabbit import RabbitRouter
from faststream.rabbit.annotations import ContextRepo

from saltbox_core.event_bus.rabbit.common_messages import (
    RunTaskEventBusMessage,
    RunTaskResultEventBusMessage,
    RunTaskStatus,
    SyncTemplatesRequestEventBusMessage,
)
from saltbox_core.scheduler.handlers import scheduler_handlers
from saltbox_core.scheduler.sync import sync_scheduler_templates
from saltbox_sdk.config.logger_config import logger
from saltbox_sdk.event_bus.utils import send_message

router = RabbitRouter(prefix='scheduler_')


@router.subscriber('sync_templates')
async def sync_templates(message: SyncTemplatesRequestEventBusMessage) -> None:
    if message.target is not None and message.target not in ['core', '*']:
        return

    await sync_scheduler_templates()


@router.subscriber('run_task')
async def run_scheduled_task(message: RunTaskEventBusMessage, context: ContextRepo) -> None:
    if message.target is not None and message.target not in ['core', '*']:
        return

    result_status = RunTaskStatus.FAILURE

    if message.fun in scheduler_handlers:
        try:
            result_data = await scheduler_handlers[message.fun](message=message, context=context)

            result_status = RunTaskStatus.SUCCESS
        except Exception as e:
            logger.error(e)
            result_data = {'error': str(e)}
    else:
        result_data = {'error': f'Unknown function `{message.fun}`'}

    result_message = RunTaskResultEventBusMessage(
        target='scheduler',
        process_id=message.process_id,
        status=result_status,
        data=result_data,
    )

    await send_message(message=result_message, queue=f'{router.prefix}run_task_result')
