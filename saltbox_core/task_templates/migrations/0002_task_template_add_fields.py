from typing import ClassVar

from saltbox_sdk.migrations.base_migration import BaseMigration
from saltbox_sdk.migrations.stages.base import BaseMigrationStage
from saltbox_sdk.migrations.stages.mongo_fields import MongoAddFieldStage


class Migration(BaseMigration):
    dependencies: ClassVar[list[str]] = ['saltbox_core.task_templates.migrations.0002_task_template_model_update']
    stages: ClassVar[list[BaseMigrationStage]] = [
        MongoAddFieldStage(
            collection_name='task_templates',
            field_name='title',
            value={},
        ),
        MongoAddFieldStage(
            collection_name='task_templates',
            field_name='description',
            value={},
        ),
        MongoAddFieldStage(
            collection_name='task_templates',
            field_name='sls_content',
            value='',
        ),
    ]
