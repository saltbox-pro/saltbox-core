import asyncio
import json
import logging.config
from typing import Any

from redis import asyncio as aioredis

from fastms_core.config import LOG_CONFIG, SETTINGS
from fastms_core.minions.crud import minion_crud
from fastms_core.minions.models import Minion
from fastms_core.minions.schemas import MinionSchemaCreate

logging.config.dictConfig(LOG_CONFIG.model_dump())

logger = logging.getLogger(__name__)


# TODO: temporary solution, need to be refactored
class GrainsConsumer:
    def __init__(self, channel: str):
        self.redis_url: str = SETTINGS.redis_url
        self.con_kwargs = SETTINGS.redis_connection_kwargs
        self.channel = channel

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
            exist = await Minion.find_one({'minion_id': minion_id})
            if exist:
                await minion_crud.update(db_obj=exist, obj_in=minion_obj)
            else:
                await minion_crud.create(obj_in=MinionSchemaCreate(**minion_obj))

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
