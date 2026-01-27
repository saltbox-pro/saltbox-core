from datetime import datetime, timezone
from typing import ClassVar

from pymongo.asynchronous.database import AsyncDatabase

from saltbox_sdk.db.migration_schemas import BaseMigration, MigrationId


class CreateIndexMigration(BaseMigration[AsyncDatabase]):
    id: ClassVar[MigrationId] = '0003__create_index'
    created_at: ClassVar[datetime] = datetime(2026, 1, 28, 14, 0, 0, tzinfo=timezone.utc)
    dependencies: ClassVar[list[MigrationId]] = ['0002__add_metadata']

    async def action(self, db: AsyncDatabase) -> None:
        _ = await db['test'].create_index('value')
