from typing import ClassVar

from saltbox_sdk.db.mongo.config import get_mongo_db
from saltbox_sdk.migrations.base_migration import BaseMigration
from saltbox_sdk.migrations.stages.base import BaseMigrationStage, RunPythonMigrationStage

BACKFILL_PIPELINE: list[dict] = [
    {'$match': {'job_id': {'$exists': False}}},
    {
        '$lookup': {
            'from': 'jobs',
            'let': {'jid': '$jid', 'salt_master': '$salt_master'},
            'pipeline': [
                {
                    '$match': {
                        '$expr': {
                            '$and': [
                                {'$eq': ['$jid', '$$jid']},
                                {'$eq': ['$salt_master', '$$salt_master']},
                            ]
                        }
                    }
                },
                {'$project': {'_id': 1}},
            ],
            'as': 'job',
        }
    },
    {'$unwind': '$job'},
    {'$project': {'job_id': '$job._id'}},
    {
        '$merge': {
            'into': 'job_returns',
            'on': '_id',
            'whenMatched': 'merge',
            'whenNotMatched': 'discard',
        }
    },
]


async def backfill_job_return_job_id() -> str:
    collection = get_mongo_db().get_collection('job_returns')

    matched_count = await collection.count_documents({'job_id': {'$exists': False}})

    if not matched_count:
        return 'Nothing to backfill'

    cursor = await collection.aggregate(BACKFILL_PIPELINE)
    await cursor.to_list()

    orphaned_count = await collection.count_documents({'job_id': {'$exists': False}})

    return f'Backfilled {matched_count - orphaned_count} of {matched_count}, orphaned left: {orphaned_count}'


class Migration(BaseMigration):
    dependencies: ClassVar[list[str]] = ['saltbox_core.jobs.migrations.0003_backfill_default_source']
    stages: ClassVar[list[BaseMigrationStage]] = [
        RunPythonMigrationStage(callback=backfill_job_return_job_id),
    ]
