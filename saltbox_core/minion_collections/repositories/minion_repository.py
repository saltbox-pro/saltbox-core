from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, ClassVar, cast, overload

import pymongo
from fastapi import Depends
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.operations import _IndexKeyHint

from saltbox_core.minion_collections.schemas.minion_schemas import MinionModel

# from saltbox_core.config import logger
from saltbox_sdk.db.mongo.config import get_mongo
from saltbox_sdk.db.mongo.repository_base import BaseMongoRepository, ProjectionModel


class MinionRepository(BaseMongoRepository[MinionModel]):
    def last_activity_seconds_query_override(self, field_name: str, field_value: Any) -> tuple[str, Any]:
        if field_name != 'last_activity_seconds':
            return field_name, field_value

        if isinstance(field_value, dict):
            lookup = cast(str, next(iter(field_value)))
            value = field_value[lookup]

            if lookup in ['$in', '$nin']:
                return 'last_activity', {
                    lookup: [datetime.now(UTC) - timedelta(seconds=float(item_val)) for item_val in value]
                }
            else:
                lookup = {'$lt': '$gt', '$lte': '$gte', '$gt': '$lt', '$gte': '$lte'}.get(lookup, lookup)
                return 'last_activity', {lookup: datetime.now(UTC) - timedelta(seconds=float(value))}
        else:
            return 'last_activity', datetime.now(UTC) - timedelta(seconds=float(field_value))

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
        query_overrides: ClassVar[dict[str, str]] = {'last_activity_seconds': 'last_activity_seconds_query_override'}
        collection_index_to_keys: ClassVar[dict[str, _IndexKeyHint]] = {
            'minion_id_master_unique_index_asc': [('minion_id', pymongo.ASCENDING), ('master', pymongo.ASCENDING)],
            'created_asc': [('created', pymongo.ASCENDING)],
            'last_activity_asc': [('last_activity', pymongo.ASCENDING)],
            'grains_text': [('grains', pymongo.TEXT)],
        }


def get_minion_repository(db: Annotated[AsyncDatabase, Depends(get_mongo)]) -> MinionRepository:
    return MinionRepository(db)
