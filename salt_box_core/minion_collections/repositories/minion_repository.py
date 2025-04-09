from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, ClassVar, overload

from fastapi import Depends
from pymongo.asynchronous.database import AsyncDatabase

from salt_box_core.db.mongo.config import get_mongo
from salt_box_core.db.mongo.repository_base import BaseMongoRepository, ProjectionModel
from salt_box_core.db.mongo.schemas_base import PyObjectId
from salt_box_core.minion_collections.schemas.minion_schemas import MinionModel


class MinionRepository(BaseMongoRepository[MinionModel]):
    def __prepare_query__(self, query: PyObjectId | dict[str, Any] | None) -> dict[str, Any]:
        query = super().__prepare_query__(query)

        last_activity_seconds: Any = query.pop('last_activity_seconds', None)
        if last_activity_seconds is not None:
            if type(last_activity_seconds) is dict:
                lookup, value = last_activity_seconds.popitem()

                if lookup in ['$in', '$nin']:
                    query['last_activity'] = {
                        lookup: [datetime.now(UTC) - timedelta(seconds=float(item_val)) for item_val in value]
                    }
                else:
                    lookup = {'$lt': '$gt', '$lte': '$gte', '$gt': '$lt', '$gte': '$lte'}.get(lookup, lookup)
                    query['last_activity'] = {lookup: datetime.now(UTC) - timedelta(seconds=float(value))}
            else:
                query['last_activity'] = datetime.now(UTC) - timedelta(seconds=float(last_activity_seconds))

        return query

    @overload
    async def get_by_master_and_id(self, master: str, minion_id: str) -> MinionModel: ...

    @overload
    async def get_by_master_and_id(
        self, master: str, minion_id: str, projection_model: type[ProjectionModel]
    ) -> ProjectionModel: ...

    async def get_by_master_and_id(
        self, master: str, minion_id: str, projection_model: type[ProjectionModel] | None = None
    ) -> ProjectionModel | MinionModel:
        query = {'master': master, 'minion_id': minion_id}

        if projection_model:
            return await self.get(query=query, projection_model=projection_model)
        else:
            return await self.get(query=query)

    class Meta:
        collection_name = 'minions'
        auto_now_add_fields: ClassVar[list[str]] = ['created']
        auto_now_fields: ClassVar[list[str]] = ['modified']


def get_minion_repository(db: Annotated[AsyncDatabase, Depends(get_mongo)]) -> MinionRepository:
    return MinionRepository(db)
