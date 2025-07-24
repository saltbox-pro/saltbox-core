import json
from typing import Any

from faststream import BaseMiddleware, context
from faststream.broker.message import StreamMessage
from faststream.types import AsyncFunc, AsyncFuncAny
from pydantic import BaseModel

from salt_box_core.config import logger
from salt_box_core.event_bus.exceptions import CreateSignError
from salt_box_core.masters.repositories.master_repository import MasterRepository, get_master_repository
from salt_box_core.masters.services.master_service import MasterService, get_master_service
from salt_box_core.utilities.gpg import SaltBoxCrypt
from saltbox_bridge_messages import CoreMessageBase
from saltbox_sdk.db.exceptions import ObjectNotFoundError
from saltbox_sdk.db.mongo.config import get_mongo_db


class MastersAuthMiddleware(BaseMiddleware):
    _crypt: SaltBoxCrypt | None = None

    def __init__(self, msg: Any | None = None) -> None:
        master_repository: MasterRepository = get_master_repository(get_mongo_db())
        self.master_service: MasterService = get_master_service(master_repository)

        super().__init__(msg)

    @property
    def crypt(self) -> SaltBoxCrypt:
        if not self._crypt:
            self._crypt = context.get('saltbox_crypt')

        if not self._crypt:
            self._crypt = SaltBoxCrypt()

        return self._crypt

    def create_signature(self, message: BaseModel | dict | str) -> str:
        if isinstance(message, BaseModel):
            sign = self.crypt.sign_str(message.model_dump_json())
        elif isinstance(message, dict):
            sign = self.crypt.sign_str(json.dumps(message))
        elif isinstance(message, str):
            sign = self.crypt.sign_str(message)
        else:
            msg = f'Unsupported message type: {type(message)}\n{message!s}'  # type: ignore[unreachable]
            raise CreateSignError(msg)

        return sign

    def validate_signature(self, message: bytes, sign: str) -> bool:
        return True  # TODO @: check message signature

    async def publish_scope(self, call_next: AsyncFunc, msg: Any, *args: Any, **kwargs: Any) -> Any:
        if not kwargs.get('headers'):  # By default, the "headers" item exists, but its value is None
            kwargs['headers'] = {}  # So "setdefault()" won't work in this situation

        kwargs['headers']['sign'] = self.create_signature(msg)

        return await super().publish_scope(call_next, msg, *args, **kwargs)

    async def consume_scope(self, call_next: AsyncFuncAny, msg: StreamMessage[Any]) -> Any:
        # sign: str | None = msg.headers.pop('sign')
        #
        # if sign is None or not self.validate_signature(message=msg.raw_message, sign=sign):
        #     return None

        message = CoreMessageBase(**await msg.decode())  # type: ignore[arg-type]

        try:
            await self.master_service.get_by_master_id(master_id=message.master)
        except ObjectNotFoundError:
            logger.error('Master %s not found', message.master)
            return None

        return await super().consume_scope(call_next, msg)
