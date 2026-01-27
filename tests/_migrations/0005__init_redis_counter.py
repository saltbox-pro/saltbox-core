from datetime import datetime, timezone
from typing import ClassVar

from redis.asyncio import Redis

from saltbox_sdk.db.migration_schemas import BaseMigration, MigrationId


class InitRedisCounterMigration(BaseMigration[Redis]):
    id: ClassVar[MigrationId] = '0005__init_redis_counter'
    comment: ClassVar[str] = 'Init redis counter'
    created_at: ClassVar[datetime] = datetime(2026, 1, 28, 16, 0, 0, tzinfo=timezone.utc)

    async def action(self, db: Redis) -> None:
        await db.set('test:counter', '0')
        await db.hset('test:meta', mapping={
            'version': '1',
            'created': datetime.now(timezone.utc).isoformat(),
        })
