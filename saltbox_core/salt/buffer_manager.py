import asyncio
import json

from redis import asyncio as aioredis
from taskiq.exceptions import SendTaskError

from saltbox_core.config import SETTINGS, logger
from saltbox_core.salt.tiq_tasks import process_salt_event_task
from saltbox_core.tkq import shutdown_broker, startup_broker
from saltbox_sdk.config.redis_config import REDIS_SETTINGS


class SaltBufferManager:
    BUFFER_CHANNEL_MASK = 'salt-events:*:to_process'

    def __init__(self) -> None:
        self.redis: aioredis.Redis | None = None

    async def get_redis(self) -> aioredis.Redis:
        if self.redis is None:
            self.redis = await aioredis.from_url(REDIS_SETTINGS.redis_url, **REDIS_SETTINGS.redis_connection_kwargs)

        return self.redis

    async def run(self) -> None:
        logger.info('Salt buffer manager are started. Waiting for messages...')

        redis_client = await self.get_redis()

        while True:
            for buffer_key in await redis_client.keys(self.BUFFER_CHANNEL_MASK):
                salt_events: list[bytes] = await redis_client.lpop(
                    name=buffer_key, count=SETTINGS.salt_buffer_manager_batch_size
                )

                if not salt_events:
                    continue

                for event_json in salt_events:
                    event = json.loads(event_json.decode())
                    try:
                        master_id = event['master_id']
                        tag = event['tag']
                        data = event['data']
                        retries = event.get('retries', 0)

                        logger.debug(f'Received salt event "{tag}" from master "{master_id}". Retries: {retries}')
                    except KeyError:
                        logger.debug('Unknown event format: %s', event)
                        continue

                    try:
                        await process_salt_event_task.kiq(master_id=master_id, tag=tag, data=data, retries=retries)
                    except SendTaskError:
                        await redis_client.lpush(buffer_key, event_json)

            await asyncio.sleep(SETTINGS.salt_buffer_manager_timeout)


def get_salt_buffer_manager() -> SaltBufferManager:
    return SaltBufferManager()


async def async_main() -> None:
    logger.info('Starting salt buffer manager...')

    buffer_manager = SaltBufferManager()

    await startup_broker()
    await buffer_manager.run()
    await shutdown_broker()


def main() -> None:
    asyncio.run(async_main())


if __name__ == '__main__':
    main()
