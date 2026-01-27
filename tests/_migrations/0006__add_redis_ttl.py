from datetime import datetime, timezone
from typing import ClassVar

from redis.asyncio import Redis

from saltbox_sdk.db.migration_schemas import BaseMigration, MigrationId


class AddRedisTTLMigration(BaseMigration[Redis]):
    id: ClassVar[MigrationId] = '0006__add_redis_ttl'
    comment: ClassVar[str] = 'Add TTL for counter'
    created_at: ClassVar[datetime] = datetime(2026, 1, 28, 17, 0, 0, tzinfo=timezone.utc)
    dependencies: ClassVar[list[MigrationId]] = ['0005__init_redis_counter']

    async def action(self, db: Redis) -> None:
        await db.expire('test:counter', 86400)
        await db.zadd('test:timestamps', {str(datetime.now(timezone.utc).timestamp()): 1})
