from typing import Any

from faststream.redis import RedisBroker, RedisMessage

from salt_box_core.event_bus.master_bus_base_messages import BusMasterMessage
from salt_box_core.event_bus.master_bus_middlewares import MastersAuthMiddleware


async def send_message_to_master(
    message: BusMasterMessage, message_tag: str, broker: RedisBroker | None = None
) -> None:
    from salt_box_core.event_bus.faststream_redis import get_faststream_broker

    if not broker:
        broker = get_faststream_broker(middlewares=[MastersAuthMiddleware])

    async with broker as br:
        await br.publish(message=message, channel=f'master_{message_tag}')


async def send_message_and_wait_response_to_master(
    message: BusMasterMessage, message_tag: str, response_timeout: float = 3.0, broker: RedisBroker | None = None
) -> Any:
    from salt_box_core.event_bus.faststream_redis import get_faststream_broker

    if not broker:
        broker = get_faststream_broker(middlewares=[MastersAuthMiddleware])

    async with broker as br:
        response: RedisMessage = await br.request(  # type: ignore
            message,
            channel=f'master_{message_tag}',
            timeout=response_timeout,
        )
        return await response.decode()
