import json
from typing import Any

from faststream import BaseMiddleware
from faststream.broker.message import StreamMessage
from faststream.types import AsyncFunc, AsyncFuncAny
from pydantic import BaseModel

from salt_box_core.config import logger
from salt_box_core.db.exceptions import ObjectNotFoundError
from salt_box_core.db.mongo.config import get_mongo_db
from salt_box_core.event_bus.master_bus_base_messages import _BusMasterMessage
from salt_box_core.masters.repositories.master_repository import MasterRepository, get_master_repository
from salt_box_core.masters.services.master_service import MasterService, get_master_service
from salt_box_core.utilities.gpg import SaltBoxCrypt


class MastersAuthMiddleware(BaseMiddleware):
    def __init__(self, msg: Any | None = None) -> None:
        master_repository: MasterRepository = get_master_repository(get_mongo_db())
        self.master_service: MasterService = get_master_service(master_repository)

        self.crypto = SaltBoxCrypt()

        super().__init__(msg)

    async def publish_scope(self, call_next: AsyncFunc, msg: Any, *args: Any, **kwargs: Any) -> Any:
        if not kwargs.get('headers'):  # By default, the "headers" item exists, but its value is None
            kwargs['headers'] = {}  # So "setdefault()" won't work in this situation

        sign = None

        if isinstance(msg, BaseModel):
            sign = self.crypto.sign_str(msg.model_dump_json())
        elif isinstance(msg, dict):
            sign = self.crypto.sign_str(json.dumps(msg))
        elif isinstance(msg, str):
            sign = self.crypto.sign_str(msg)

        kwargs['headers']['sign'] = sign

        return await super().publish_scope(call_next, msg, *args, **kwargs)

    async def consume_scope(self, call_next: AsyncFuncAny, msg: StreamMessage[Any]) -> Any:
        # sign: str | None = msg.headers.get('sign')  # TODO @: verify message signature
        message = _BusMasterMessage(**await msg.decode())  # type: ignore

        try:
            await self.master_service.get_by_master_id(master_id=message.master)
        except ObjectNotFoundError:
            logger.error(f'Master "{message.master}" not found')
            return None

        # if sign and sign != self.crypto.verify_str(message):
        #     return None

        return await super().consume_scope(call_next, msg)
