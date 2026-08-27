from typing import ClassVar

from saltbox_sdk.migrations.base_migration import BaseMigration
from saltbox_sdk.migrations.stages.base import BaseMigrationStage
from saltbox_sdk.migrations.stages.mongo_fields import MongoSetFieldStage

DEFAULT_SOURCE_VALUE: dict = {'type': 'system', 'id': None}


class Migration(BaseMigration):
    dependencies: ClassVar[list[str]] = ['saltbox_core.tasks.migrations.0001_init']
    stages: ClassVar[list[BaseMigrationStage]] = [
        MongoSetFieldStage(
            collection_name='tasks',
            field_name='source',
            value=DEFAULT_SOURCE_VALUE,
            mongo_filter={'source': None},
        ),
    ]
