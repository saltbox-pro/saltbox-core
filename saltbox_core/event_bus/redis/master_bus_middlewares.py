from typing import Any

from faststream import BaseMiddleware
from faststream.broker.message import StreamMessage
from faststream.types import AsyncFuncAny

from saltbox_bridge_messages import CoreMessageBase
from saltbox_core.config import logger
from saltbox_core.masters.repositories.master_repository import MasterRepository, get_master_repository
from saltbox_core.masters.services.master_service import MasterService, get_master_service
from saltbox_sdk.db.mongo.config import get_mongo_db
from saltbox_sdk.exceptions import ObjectNotFoundException


class MastersAuthMiddleware(BaseMiddleware):
    def __init__(self, msg: Any | None = None) -> None:
        master_repository: MasterRepository = get_master_repository(get_mongo_db())
        self.master_service: MasterService = get_master_service(master_repository)

        super().__init__(msg)

    async def consume_scope(self, call_next: AsyncFuncAny, msg: StreamMessage[Any]) -> Any:
        message = CoreMessageBase(**await msg.decode())  # type: ignore[arg-type]

        try:
            await self.master_service.get_by_master_id(master_id=message.master)
        except ObjectNotFoundException:
            logger.exception('Master %s not found', message.master)
            return None

        return await super().consume_scope(call_next, msg)
