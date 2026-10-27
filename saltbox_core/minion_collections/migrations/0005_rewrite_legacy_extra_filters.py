from typing import Any, ClassVar

from pymongo import UpdateOne

from saltbox_sdk.db.mongo.config import get_mongo_db
from saltbox_sdk.migrations.base_migration import BaseMigration
from saltbox_sdk.migrations.stages.base import BaseMigrationStage, RunPythonMigrationStage

BULK_SIZE = 500
LEGACY_EXTRA_PREFIXES = ('extra.static.', 'extra.aggregated.')
QUERY_FIELDS_BY_COLLECTION = {
    'minion_collections': ['query', 'full_query'],
    'task_templates': ['query'],
    'tasks': ['target_query'],
}


def rewrite_key(key: str, category_keys: set[tuple[str, str]]) -> str:
    for prefix in LEGACY_EXTRA_PREFIXES:
        if not key.startswith(prefix):
            continue

        parts = key.split('.')
        if len(parts) > 3 and (parts[1], parts[2]) in category_keys:
            return key

        return 'extra.' + key.removeprefix(prefix)

    return key


def rewrite_query(query: Any, category_keys: set[tuple[str, str]]) -> Any:
    if isinstance(query, dict):
        return {rewrite_key(key, category_keys): rewrite_query(value, category_keys) for key, value in query.items()}

    if isinstance(query, list):
        return [rewrite_query(item, category_keys) for item in query]

    return query


async def rewrite_legacy_extra_filters() -> str:
    db = get_mongo_db()

    category_keys: set[tuple[str, str]] = set()
    async for category in db.get_collection('minion_extra_data_category').find({}, {'source': 1, 'name': 1}):
        category_keys.add((category['source'], category['name']))

    report = []

    for collection_name, fields in QUERY_FIELDS_BY_COLLECTION.items():
        collection = db.get_collection(collection_name)
        operations: list[UpdateOne] = []
        rewritten_count = 0

        async for doc in collection.find({}, dict.fromkeys(fields, 1)):
            update = {}
            for field in fields:
                if field not in doc:
                    continue

                rewritten = rewrite_query(doc[field], category_keys)
                if rewritten != doc[field]:
                    update[field] = rewritten

            if not update:
                continue

            operations.append(UpdateOne({'_id': doc['_id']}, {'$set': update}))
            rewritten_count += 1

            if len(operations) >= BULK_SIZE:
                await collection.bulk_write(operations)
                operations = []

        if operations:
            await collection.bulk_write(operations)

        report.append(f'{collection_name}: {rewritten_count}')

    return f'Rewritten legacy extra filters ({", ".join(report)})'


class Migration(BaseMigration):
    dependencies: ClassVar[list[str]] = ['saltbox_core.minion_collections.migrations.0004_single_type_extra_fields']
    stages: ClassVar[list[BaseMigrationStage]] = [
        RunPythonMigrationStage(callback=rewrite_legacy_extra_filters),
    ]
