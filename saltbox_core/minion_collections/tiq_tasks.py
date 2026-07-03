from saltbox_core.config import logger
from saltbox_core.event_bus.rabbit.exchanges import exchanges
from saltbox_core.tkq import broker, queue_default
from saltbox_sdk.event_bus.schemas import EventBusBaseMessage
from saltbox_sdk.event_bus.utils import send_message


@broker.task(
    queue_name=queue_default.name, schedule=[{'cron': '*/5 * * * *', 'labels': {'queue_name': queue_default.name}}]
)
async def request_extra_data_categories() -> None:
    logger.warning('request_extra_data_categories')
    await send_message(
        message=EventBusBaseMessage(sender='core'),
        exchange=exchanges['core_sync_extra_data_categories'],
    )
