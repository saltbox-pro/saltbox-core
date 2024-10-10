from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from motor.core import AgnosticDatabase

from fastms_core.minions.models import Minion
from fastms_core.minions.schemas import MinionSchemaCreate, MinionSchemaUpdate
from fastms_core.utilities.mongo_crud_base import CRUDBase

logger = logging.getLogger(__name__)


class CRUDMinion(CRUDBase[Minion, MinionSchemaCreate, MinionSchemaUpdate]):
    async def get_by_id(self, db: AgnosticDatabase, *, minion_id: str) -> Minion | None:
        return await self.engine.find_one(Minion, Minion.minion_id == minion_id)

    async def update(
        self, db: AgnosticDatabase, *, db_obj: Minion, obj_in: MinionSchemaUpdate | dict[str, Any]
    ) -> Minion:
        if isinstance(obj_in, dict):
            update_data = obj_in
        else:
            update_data = obj_in.model_dump(exclude_unset=True)
            update_data['modified'] = datetime.now().astimezone()
        return await super().update(db, db_obj=db_obj, obj_in=update_data)


minion_crud = CRUDMinion(Minion)
