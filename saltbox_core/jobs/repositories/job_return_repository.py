import json
from typing import Annotated, Any, ClassVar

from fastapi import Depends
from pymongo.asynchronous.database import AsyncDatabase
from redis.asyncio import Redis

from saltbox_core.jobs.schemas.job_return_schemas import JobReturnModel
from saltbox_sdk.db.mongo.config import get_mongo
from saltbox_sdk.db.mongo.repository_base import BaseMongoRepository
from saltbox_sdk.db.redis.config import get_redis


class JobReturnRepository(BaseMongoRepository[JobReturnModel]):
    class Meta:
        collection_name = 'job_returns'
        auto_now_add_fields: ClassVar[list[str]] = ['created']
        auto_now_fields: ClassVar[list[str]] = ['modified']

    def __init__(self, database: AsyncDatabase, rdb: Redis):
        self.rdb = rdb
        super().__init__(database=database)

    async def prepare_object_data(self, data: dict[str, Any]) -> dict[str, Any]:
        data = await super().prepare_object_data(data=data)
        raw_return: bytes | None = await self.rdb.hget(
            name=f'master:{data["salt_master"]}:job:{data["jid"]}:return-data', key=data['minion_id']
        )

        if raw_return:
            data['data'] = json.loads(raw_return)

        return data


def get_job_return_repository(
    db: Annotated[AsyncDatabase, Depends(get_mongo)],
    rdb: Annotated[Redis, Depends(get_redis)],
) -> JobReturnRepository:
    return JobReturnRepository(database=db, rdb=rdb)
