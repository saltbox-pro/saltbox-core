from typing import Annotated

from fastapi import Depends
from redis.asyncio import Redis

from saltbox_core.config import SETTINGS
from saltbox_core.minion_collections.schemas.collection_membership_run import CollectionMembershipRun
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.db.redis.config import get_redis


class CollectionMembershipRunRepository:
    def __init__(self, rdb: Redis) -> None:
        self.rdb = rdb

    async def save(self, collection_id: PyObjectId, run: CollectionMembershipRun) -> None:
        key = f'collection-membership:{collection_id}:runs'
        expires_at = int(run.started_at.timestamp() * 1000) + SETTINGS.membership_run_history_ttl * 1000
        async with self.rdb.pipeline(transaction=True) as pipe:
            pipe.hset(key, run.id, run.model_dump_json())
            pipe.execute_command('HPEXPIREAT', key, expires_at, 'FIELDS', 1, run.id)
            await pipe.execute()

    async def get_list(self, collection_id: PyObjectId) -> list[CollectionMembershipRun]:
        values = await self.rdb.hvals(f'collection-membership:{collection_id}:runs')
        runs = [CollectionMembershipRun.model_validate_json(value) for value in values]
        return sorted(runs, key=lambda run: (run.started_at, run.id))

    async def get_lists(self, collection_ids: list[PyObjectId]) -> dict[PyObjectId, list[CollectionMembershipRun]]:
        async with self.rdb.pipeline(transaction=False) as pipe:
            for collection_id in collection_ids:
                pipe.hvals(f'collection-membership:{collection_id}:runs')
            values = await pipe.execute()
        return {
            collection_id: [CollectionMembershipRun.model_validate_json(value) for value in records]
            for collection_id, records in zip(collection_ids, values, strict=True)
        }


def get_collection_membership_run_repository(
    rdb: Annotated[Redis, Depends(get_redis)],
) -> CollectionMembershipRunRepository:
    return CollectionMembershipRunRepository(rdb)
