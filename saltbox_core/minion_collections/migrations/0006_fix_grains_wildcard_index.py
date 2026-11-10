from typing import ClassVar

import pymongo

from saltbox_sdk.db.mongo.config import get_mongo_db
from saltbox_sdk.migrations.base_migration import BaseMigration
from saltbox_sdk.migrations.stages.base import BaseMigrationStage, RunPythonMigrationStage


async def fix_grains_wildcard_index() -> str:
    collection = get_mongo_db().get_collection('minions')
    index_name = 'grains_wildcard'
    keys = [('grains.$**', pymongo.ASCENDING)]
    indexes = await collection.index_information()

    if index_name in indexes:
        if indexes[index_name]['key'] == keys:
            return 'Grains wildcard index is already correct'
        await collection.drop_index(index_name)

    await collection.create_index(keys, name=index_name)
    return 'Created grains wildcard index on grains.$**'


class Migration(BaseMigration):
    dependencies: ClassVar[list[str]] = ['saltbox_core.minion_collections.migrations.0005_rewrite_legacy_extra_filters']
    stages: ClassVar[list[BaseMigrationStage]] = [
        RunPythonMigrationStage(callback=fix_grains_wildcard_index),
    ]
