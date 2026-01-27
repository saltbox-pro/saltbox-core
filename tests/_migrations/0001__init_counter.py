from datetime import datetime, timezone
from typing import ClassVar

from pymongo.asynchronous.database import AsyncDatabase

from saltbox_sdk.db.migration_schemas import BaseMigration, MigrationId


class InitCounterMigration(BaseMigration[AsyncDatabase]):
    id: ClassVar[MigrationId] = '0001__init_counter'
    created_at: ClassVar[datetime] = datetime(2026, 1, 28, 12, 0, 0, tzinfo=timezone.utc)

    async def action(self, db: AsyncDatabase) -> None:
        _ = await db['test'].replace_one(
                    {'_id': 'counter'},
                    {'_id': 'counter', 'value': 0},
                    upsert=True
                )
