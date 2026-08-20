from typing import ClassVar

from saltbox_sdk.migrations.base_migration import BaseMigration
from saltbox_sdk.migrations.stages.base import BaseMigrationStage
from saltbox_sdk.migrations.stages.mongo_collections import MongoDropCollectionStage


class Migration(BaseMigration):
    dependencies: ClassVar[list[str]] = ['saltbox_core.jobs.migrations.0001_init']
    stages: ClassVar[list[BaseMigrationStage]] = [MongoDropCollectionStage(collection_name='job_schemas')]
