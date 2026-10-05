from typing import Any, ClassVar

from bson import ObjectId
from pymongo import UpdateOne

from saltbox_sdk.db.mongo.config import get_mongo_db
from saltbox_sdk.migrations.base_migration import BaseMigration
from saltbox_sdk.migrations.stages.base import BaseMigrationStage, RunPythonMigrationStage
from saltbox_sdk.utilities.helpers import utc_now

BULK_SIZE = 500


def identify_entry(entry: dict[str, Any]) -> dict[str, Any] | None:
    if '_id' in entry:
        return None

    data = dict(entry.get('data') or {})
    updated_at = data.pop('updated_at', None)

    return {
        '_id': ObjectId(),
        'minion_id': entry['minion_id'],
        'is_system': True,
        'updated_at': updated_at or utc_now(),
        'data': data,
    }


async def identify_extra_aggregated_entries() -> str:
    collection = get_mongo_db().get_collection('minion_extra_data')
    cursor = collection.find({'minions': {'$elemMatch': {'_id': {'$exists': False}}}}, {'minions': 1})

    operations: list[UpdateOne] = []
    identified_entries = 0

    async for record in cursor:
        new_entries = []
        for entry in record['minions']:
            identified = identify_entry(entry)
            new_entries.append(identified or entry)
            if identified is not None:
                identified_entries += 1

        operations.append(UpdateOne({'_id': record['_id']}, {'$set': {'minions': new_entries}}))

        if len(operations) >= BULK_SIZE:
            await collection.bulk_write(operations)
            operations = []

    if operations:
        await collection.bulk_write(operations)

    return f'Identified {identified_entries} extra aggregated entry(ies)'


class Migration(BaseMigration):
    dependencies: ClassVar[list[str]] = ['saltbox_core.minion_collections.migrations.0002_wrap_extra_static_items']
    stages: ClassVar[list[BaseMigrationStage]] = [
        RunPythonMigrationStage(callback=identify_extra_aggregated_entries),
    ]
