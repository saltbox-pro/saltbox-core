from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Generic, TypeVar

from fastapi.encoders import jsonable_encoder
from motor.core import AgnosticDatabase
from odmantic import AIOEngine, Model
from pydantic import BaseModel

from fastms_core.db.mongo import get_engine
from fastms_core.minions.models import Minion
from fastms_core.minions.schemas import MinionSchemaCreate, MinionSchemaUpdate

ModelType = TypeVar('ModelType', bound=Model)
CreateSchemaType = TypeVar('CreateSchemaType', bound=BaseModel)
UpdateSchemaType = TypeVar('UpdateSchemaType', bound=BaseModel)

logger = logging.getLogger(__name__)


class CRUDBase(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    def __init__(self, model: type[ModelType]):
        """
        CRUD object with default methods to Create, Read, Update, Delete (CRUD).

        **Parameters**

        * `model`: A odmantic model class
        * `schema`: A Pydantic model (schema) class
        """
        self.model = model
        self.engine: AIOEngine = get_engine()

    async def get(self, db: AgnosticDatabase, id: Any) -> ModelType | None:
        return await self.engine.find_one(self.model, self.model.id == id)

    async def get_multi(
        self, db: AgnosticDatabase, search: dict | None, *, page: int = 0, per_page: int = 20, page_break: bool = False
    ) -> list[ModelType]:
        skip = page * per_page if page_break else 0
        limit = per_page if page_break else None
        if search:
            query_expr = {k: v for k, v in search.items() if v}
        else:
            query_expr = {}
        return await self.engine.find(self.model, query_expr, sort=None, skip=skip, limit=limit)

    async def create(self, db: AgnosticDatabase, *, obj_in: CreateSchemaType) -> ModelType:
        obj_in_data = jsonable_encoder(obj_in)
        db_obj = self.model(**obj_in_data)
        return await self.engine.save(db_obj)

    async def update(
        self, db: AgnosticDatabase, *, db_obj: ModelType, obj_in: UpdateSchemaType | dict[str, Any]
    ) -> ModelType:
        obj_data = jsonable_encoder(db_obj)
        if isinstance(obj_in, dict):
            update_data = obj_in
        else:
            update_data = obj_in.model_dump(exclude_unset=True)
        for field in obj_data:
            if field in update_data:
                setattr(db_obj, field, update_data[field])
        # TODO: Check if this saves changes with the setattr calls
        await self.engine.save(db_obj)
        return db_obj

    async def remove(self, db: AgnosticDatabase, *, id: int) -> ModelType | None:
        obj = await self.engine.find_one(self.model, self.model.id == id)
        if obj:
            await self.engine.delete(obj)
        return obj


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
