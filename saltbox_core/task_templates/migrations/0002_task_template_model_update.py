from typing import ClassVar

from saltbox_sdk.migrations.base_migration import BaseMigration
from saltbox_sdk.migrations.stages.base import BaseMigrationStage
from saltbox_sdk.migrations.stages.mongo_fields import MongoAddFieldStage, MongoRemoveFieldStage


class Migration(BaseMigration):
    dependencies: ClassVar[list[str]] = ['saltbox_core.task_templates.migrations.0001_init']
    stages: ClassVar[list[BaseMigrationStage]] = [
        MongoAddFieldStage(
            collection_name='task_templates',
            field_name='schema_rel_path',
            value=None,
        ),
        MongoAddFieldStage(
            collection_name='task_templates',
            field_name='query',
            value={},
        ),
        MongoRemoveFieldStage(
            collection_name='task_templates',
            field_name='source_hash',
        ),
    ]
