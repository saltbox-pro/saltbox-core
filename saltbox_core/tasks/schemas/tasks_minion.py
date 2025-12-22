from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, computed_field

from saltbox_sdk.db.mongo.schemas_base import IDMixin, PyObjectId, QueryParams, SortParams
from saltbox_sdk.db.schemas_base import CreatedModifiedMixin, SkipLimitParams
from saltbox_sdk.utilities.helpers import Iso8601ZDatetime as TimezoneAwareDatetime

# Task minion


class MinionDataSchema(BaseModel):
    minion_id: str = Field(title='Minion ID')
    master: str = Field(title='Master')
    last_activity: TimezoneAwareDatetime | None = Field(title='Last activity', default=None)


class TaskMinionStatus(StrEnum):
    pending = 'pending'
    busy = 'busy'
    in_work = 'in_work'
    success = 'success'
    failed = 'failed'


class TaskMinionJobStatus(StrEnum):
    created = 'created'
    in_work = 'in_work'
    success = 'success'
    failed = 'failed'
    ignored = 'ignored'


class TaskMinionReadOnlyFieldsMixin:
    task_id: PyObjectId = Field(title='Task ID')
    minion_inner_id: PyObjectId = Field(title='Minion Mongo ID')


class TaskMinionEditableFieldsMixin:
    status: TaskMinionStatus = Field(title='Status', default=TaskMinionStatus.pending)

    jobs: dict[str, TaskMinionJobStatus] = Field(title='Jobs', default={})

    start_last_dt: TimezoneAwareDatetime | None = Field(title='Last job start dt', default=None)
    finished_dt: TimezoneAwareDatetime | None = Field(title='Processing finished dt', default=None)


class TaskMinionCreateSchema(BaseModel, TaskMinionReadOnlyFieldsMixin, TaskMinionEditableFieldsMixin): ...


class TaskMinionUpdateSchema(BaseModel, TaskMinionEditableFieldsMixin):
    model_config = ConfigDict(extra='ignore')


class TaskMinionJoinedFieldsMixin:
    minion_data: MinionDataSchema = Field(title='Minion Data')


class TaskMinionModel(
    BaseModel,
    TaskMinionJoinedFieldsMixin,
    CreatedModifiedMixin,
    TaskMinionReadOnlyFieldsMixin,
    TaskMinionEditableFieldsMixin,
    IDMixin,
):
    @computed_field(title='Count job runs')
    def count_runs(self) -> int:
        return len(self.jobs)


# REST


class TaskMinionListBody(SkipLimitParams, QueryParams, SortParams):
    model_config = ConfigDict(
        extra='ignore',
    )
