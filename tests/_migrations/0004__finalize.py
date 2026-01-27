from datetime import datetime, timezone
from typing import ClassVar

from pymongo.asynchronous.database import AsyncDatabase

from saltbox_sdk.db.migration_schemas import BaseMigration, MigrationId


class FinalizeMigration(BaseMigration[AsyncDatabase]):
    id: ClassVar[MigrationId] = '0004__finalize'
    comment: ClassVar[str] = 'Finalize test migration with setup status flag'
    created_at: ClassVar[datetime] = datetime(2026, 1, 28, 15, 0, 0, tzinfo=timezone.utc)
    dependencies: ClassVar[list[MigrationId]] = ['0001__init_counter', '0003__create_index']

    async def action(self, db: AsyncDatabase) -> None:
        _ = await db['test'].update_one(
            {'_id': 'counter'},
            {'$set': {'status': 'ready', 'finalized_at': datetime.now(timezone.utc)}}
        )
