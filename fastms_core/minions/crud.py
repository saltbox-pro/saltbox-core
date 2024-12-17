import logging.config

from fastms_core.config import LOG_CONFIG
from fastms_core.db.mongo.crud_base import CRUDBase
from fastms_core.minions.models import Minion
from fastms_core.minions.schemas import (
    MinionListSchema,
    MinionSchemaCreate,
    MinionSchemaUpdate,
)

logging.config.dictConfig(LOG_CONFIG.model_dump())

logger = logging.getLogger(__name__)


class CRUDMinion(CRUDBase[Minion, MinionListSchema, MinionSchemaCreate, MinionSchemaUpdate]):
    async def get_by_minion_id(self, minion_id: str) -> Minion | None:
        return await self.model.find_one({'minion_id': minion_id})


minions_crud = CRUDMinion(Minion)
