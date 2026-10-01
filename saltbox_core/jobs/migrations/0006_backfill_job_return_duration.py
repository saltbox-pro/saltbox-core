from typing import ClassVar

from saltbox_sdk.db.mongo.config import get_mongo_db
from saltbox_sdk.migrations.base_migration import BaseMigration
from saltbox_sdk.migrations.stages.base import BaseMigrationStage, RunPythonMigrationStage

BACKFILL_FILTER: dict = {
    'duration_ms': {'$exists': False},
    'stamp': {'$ne': None},
    'stamp_job': {'$ne': None},
    '$expr': {'$gte': ['$stamp', '$stamp_job']},
}

BACKFILL_UPDATE: list[dict] = [
    {'$set': {'duration_ms': {'$toLong': {'$subtract': ['$stamp', '$stamp_job']}}}},
]


async def backfill_job_return_duration() -> str:
    collection = get_mongo_db().get_collection('job_returns')

    result = await collection.update_many(filter=BACKFILL_FILTER, update=BACKFILL_UPDATE)

    return f'Backfilled `duration_ms` for {result.modified_count} of {result.matched_count} job returns'


class Migration(BaseMigration):
    dependencies: ClassVar[list[str]] = ['saltbox_core.jobs.migrations.0005_backfill_job_ttl']
    stages: ClassVar[list[BaseMigrationStage]] = [
        RunPythonMigrationStage(callback=backfill_job_return_duration),
    ]
