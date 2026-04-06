from typing import ClassVar

from saltbox_sdk.migrations.base_migration import BaseMigration
from saltbox_sdk.migrations.stages.base import BaseMigrationStage


class Migration(BaseMigration):
    dependencies: ClassVar[list[str]] = []
    stages: ClassVar[list[BaseMigrationStage]] = []
