from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from saltbox_sdk.db.mongo.schemas_base import IDMixin, PyObjectId, QueryParams, SortParams
from saltbox_sdk.db.schemas_base import CreatedModifiedMixin, SkipLimitParams

# Task status


class TaskStatus(StrEnum):
    created = 'created'
    wait_minions = 'wait_minions'
    running = 'running'
    stopping = 'stopping'
    stopped = 'stopped'
    finished = 'finished'


ACTIVE_TASK_STATUSES = (TaskStatus.wait_minions, TaskStatus.running, TaskStatus.stopping)


class TaskStatusReadOnlyFieldsMixin(BaseModel):
    task_id: PyObjectId = Field(title='Task ID')

    type: TaskStatus = Field(title='Status')


class TaskStatusEditableFieldsMixin(BaseModel):
    data: dict = Field(title='Status data', default_factory=dict)


class TaskStatusCreateSchema(TaskStatusReadOnlyFieldsMixin, TaskStatusEditableFieldsMixin): ...


class TaskStatusUpdateSchema(TaskStatusEditableFieldsMixin):
    model_config = ConfigDict(extra='ignore')


class TaskStatusModel(
    TaskStatusReadOnlyFieldsMixin, TaskStatusEditableFieldsMixin, CreatedModifiedMixin, IDMixin, BaseModel
): ...


# REST


class TaskStatusListBody(SkipLimitParams, QueryParams, SortParams):
    model_config = ConfigDict(
        extra='ignore',
    )
