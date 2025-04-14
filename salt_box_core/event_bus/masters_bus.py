import hashlib
from collections.abc import Awaitable, Callable
from typing import Any

from faststream import BaseMiddleware
from faststream.broker.message import StreamMessage
from faststream.redis import RedisBroker, RedisMessage
from pydantic import BaseModel, ConfigDict

from salt_box_core.config import logger
from salt_box_core.db.exceptions import ObjectNotFoundError
from salt_box_core.db.mongo.config import get_mongo_db
from salt_box_core.masters.repositories.master_repository import MasterRepository, get_master_repository
from salt_box_core.masters.schemas.master_schemas import (
    MasterCreateSchema,
    MasterModel,
    MasterStatus,
    MasterUpdateSchema,
)
from salt_box_core.masters.services.master_service import MasterService, get_master_service


class AuthMessage(BaseModel):
    master: str
    secret: str


class MasterSecretIsEmptyError(Exception): ...


class _BusMasterMessage(BaseModel):
    checksum: str | None = None
    master: str

    async def _get_master_secret(self) -> str | None:
        # TODO @: use cache to get master secret
        master_repository: MasterRepository = get_master_repository(get_mongo_db())
        master_service: MasterService = get_master_service(master_repository)

        master: MasterModel = await master_service.get_by_name_or_alias(value=self.master)

        if master.secret:
            return master.secret

        return None

    async def _get_checksum(self) -> str:
        master_secret = await self._get_master_secret()

        if not master_secret:
            raise MasterSecretIsEmptyError()

        message = self.model_dump_json(exclude={'checksum'})

        return hashlib.sha256(f'{self.master}_{message}_{master_secret}'.encode()).hexdigest()

    async def fill_checksum(self) -> None:
        try:
            self.checksum = await self._get_checksum()
        except MasterSecretIsEmptyError:
            self.checksum = None

    async def check_checksum(self) -> bool:
        try:
            return self.checksum == await self._get_checksum()
        except ObjectNotFoundError:
            return False
        except MasterSecretIsEmptyError:
            return False

    model_config = ConfigDict(extra='allow')


class BusMasterMessage(_BusMasterMessage):
    model_config = ConfigDict(extra='ignore')


class MastersAuthMiddleware(BaseMiddleware):
    def __init__(self, msg: Any | None = None) -> None:
        master_repository: MasterRepository = get_master_repository(get_mongo_db())
        self.master_service: MasterService = get_master_service(master_repository)

        super().__init__(msg)

    async def __auth_master(self, msg: StreamMessage[Any]) -> tuple[bool, str]:
        message = AuthMessage(**await msg.decode())  # type: ignore
        master_key = message.master
        secret = message.secret

        try:
            master: MasterModel = await self.master_service.get_by_name_or_alias(master_key)

            if not master.secret:
                master_secret = None
            else:
                master_secret = master.secret

            if not master_secret:
                await self.master_service.update(
                    query=master.id,
                    data=MasterUpdateSchema.model_validate({**master.model_dump(), 'secret': secret}),
                )
                return False, master_key
            else:
                return master_secret == secret, master_key
        except ObjectNotFoundError:
            await self.master_service.create(
                MasterCreateSchema.model_validate({'title': master_key, 'name': master_key, 'secret': secret})
            )

            return False, master_key

    async def consume_scope(self, call_next: Callable[[Any], Awaitable[Any]], msg: StreamMessage[Any]) -> Any:
        if msg.raw_message['channel'] == 'master_auth':
            auth_result, master_key = await self.__auth_master(msg)
            if auth_result:
                logger.info(f'Master auth success: {master_key}')
            else:
                logger.info(f'Master auth failed: {master_key}')
            return

        message = _BusMasterMessage(**await msg.decode())  # type: ignore

        if await message.check_checksum():
            master: MasterModel = await self.master_service.get_by_name_or_alias(message.master)

            if master.status == MasterStatus.accepted:
                return await super().consume_scope(call_next, msg)
            else:
                logger.info(f'Master are not accepted: {master.name} - {master.status}')
        else:
            logger.error(f'Message checksum failed from master: {message.master}.')


async def send_message_to_master(
    message: BusMasterMessage, message_tag: str, broker: RedisBroker | None = None
) -> None:
    from salt_box_core.event_bus.faststream_redis import get_faststream_broker

    if not broker:
        broker = get_faststream_broker()

    async with broker as br:
        await message.fill_checksum()

        await br.publish(message=message, channel=f'master_{message_tag}')


async def send_message_and_wait_response_to_master(
    message: BusMasterMessage, message_tag: str, response_timeout: float = 3.0, broker: RedisBroker | None = None
) -> Any:
    from salt_box_core.event_bus.faststream_redis import get_faststream_broker

    if not broker:
        broker = get_faststream_broker()

    async with broker as br:
        await message.fill_checksum()

        response: RedisMessage = await br.request(  # type: ignore
            message,
            channel=f'master_{message_tag}',
            timeout=response_timeout,
        )
        return await response.decode()
