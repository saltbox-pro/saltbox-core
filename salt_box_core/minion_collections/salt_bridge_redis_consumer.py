import asyncio
import json
from collections.abc import Callable
from datetime import UTC, datetime

from redis import asyncio as aioredis

from salt_box_core.config import SETTINGS, logger
from salt_box_core.db.exceptions import ObjectNotFoundError
from salt_box_core.db.mongo.config import get_mongo_db
from salt_box_core.minion_collections.repositories.minion_repository import MinionRepository
from salt_box_core.minion_collections.schemas.minion_schemas import (
    GrainsSchema,
    MinionCreateSchema,
    MinionModel,
    MinionUpdateSchema,
)


class SaltBridgeRedisConsumer:
    def __init__(self) -> None:
        self.redis_url: str = SETTINGS.redis_url
        self.con_kwargs = SETTINGS.redis_connection_kwargs
        self.repository = MinionRepository(get_mongo_db())

    @property
    def handlers(self) -> dict[str, Callable]:
        return {
            'grains': self.handle_grains,
            'presence': self.handle_presence,
        }

    async def handle_grains(self, message: dict) -> None:
        logger.debug('Received grains message: %s', message)

        minion_id = message['id']
        master = message['master']

        if message:
            try:
                minion: MinionModel = await self.repository.get_by_master_and_id(master=master, minion_id=minion_id)
                minion.grains = GrainsSchema(**message)
                await self.repository.update(minion.id, MinionUpdateSchema(**minion.model_dump()))
            except ObjectNotFoundError:
                minion_obj = {
                    'minion_id': minion_id,
                    'master': master,
                    'grains': message,
                }
                await self.repository.create(MinionCreateSchema(**minion_obj))

    async def handle_presence(self, message: dict) -> None:
        logger.debug('Received presence message: %s', message)
        last_activity_dt = datetime.fromtimestamp(message['stamp'], tz=UTC)

        for minion_id in message.get('minions', []):
            try:
                minion: MinionModel = await self.repository.get_by_master_and_id(
                    master=message['master'], minion_id=minion_id
                )
                minion.last_activity = last_activity_dt
                await self.repository.update(minion.id, MinionUpdateSchema(**minion.model_dump()))
            except ObjectNotFoundError:
                continue

    async def consume(self) -> None:
        redis = await aioredis.from_url(self.redis_url, **self.con_kwargs)
        logger.debug('Connected to redis: %s', self.redis_url)
        async with redis.pubsub() as pubsub:
            for channel in self.handlers.keys():
                await pubsub.subscribe(channel)
                logger.debug('Subscribed to channel: %s', channel)

            while True:
                msg = await pubsub.get_message()
                if msg:
                    msg_type = msg['type']

                    if msg_type != 'message':
                        continue

                    channel = msg['channel'].decode()
                    msg_data = json.loads(msg['data'])

                    handler = self.handlers.get(channel)

                    if handler:
                        await handler(msg_data)
                await asyncio.sleep(0.01)


async def async_main() -> None:
    consumer = SaltBridgeRedisConsumer()

    logger.info('Starting salt bridge redis consumer')
    await consumer.consume()


def main() -> None:
    asyncio.run(async_main())


if __name__ == '__main__':
    main()
