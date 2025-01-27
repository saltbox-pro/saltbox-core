import asyncio
import json
from typing import Any

from redis import asyncio as aioredis

from fastms_core.config import SETTINGS, logger
from fastms_core.minion_collections.repository import MinionRepository
from fastms_core.minion_collections.schemas.minion_schemas import MinionCreateSchema


# TODO (a.baikov): temporary solution, need to be refactored
class GrainsConsumer:
    def __init__(self, channel: str):
        self.redis_url: str = SETTINGS.redis_url
        self.con_kwargs = SETTINGS.redis_connection_kwargs
        self.channel = channel
        self.repository = MinionRepository()

    async def handle_message(self, message: Any) -> None:
        if not isinstance(message, bytes):
            return
        message = message.decode()
        data = json.loads(message)
        minion_id = data.get('id', '')

        minion_obj = {
            'minion_id': minion_id,
            'master': data.get('master', ''),
            'grains': data,
        }

        if data:
            exist = await self.repository.find_one({'minion_id': minion_id})
            if exist:
                await self.repository.update_one({'minion_id': minion_id}, obj_in=minion_obj)
            else:
                await self.repository.add(MinionCreateSchema(**minion_obj))

    async def consume(self) -> None:
        redis = await aioredis.from_url(self.redis_url, **self.con_kwargs)
        logger.debug('Connected to redis: %s', self.redis_url)
        async with redis.pubsub() as pubsub:
            await pubsub.subscribe(self.channel)
            logger.debug('Subscribed to channel: %s', self.channel)

            while True:
                msg = await pubsub.get_message()
                if msg:
                    await self.handle_message(msg['data'])
                await asyncio.sleep(0.01)


async def async_main() -> None:
    grains_consumer = GrainsConsumer(channel='grains')

    logger.info('Starting grains consumer')
    await grains_consumer.consume()


def main() -> None:
    asyncio.run(async_main())


if __name__ == '__main__':
    main()
