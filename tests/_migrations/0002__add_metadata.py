from datetime import datetime, timezone
from typing import ClassVar

from pymongo.asynchronous.database import AsyncDatabase

from saltbox_sdk.db.migration_schemas import BaseMigration, MigrationId


class AddMetadataMigration(BaseMigration[AsyncDatabase]):
    id: ClassVar[MigrationId] = '0002__add_metadata'
    created_at: ClassVar[datetime] = datetime(2026, 1, 28, 13, 0, 0, tzinfo=timezone.utc)
    dependencies: ClassVar[list[MigrationId]] = ['0001__init_counter']

    async def action(self, db: AsyncDatabase) -> None:
        _ = await db['test'].update_one(
            {'_id': 'counter'},
            {'$set': {'metadata': {'created': datetime.now(timezone.utc), 'version': 1}}}
        )
