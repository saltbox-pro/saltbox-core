from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from saltbox_core.jobs.schemas.job_return_schemas import JobReturnStatus
from saltbox_sdk.db.mongo.schemas_base import IDMixin, PyObjectId, QueryParams, SortParams
from saltbox_sdk.db.schemas_base import CreatedModifiedMixin, SkipLimitParams
from saltbox_sdk.utilities.helpers import Iso8601ZDatetime as TimezoneAwareDatetime

# Task minion


class TaskMinionStatus(StrEnum):
    pending = 'pending'
    busy = 'busy'
    in_work = 'in_work'
    success = 'success'
    failed = 'failed'


class TaskMinionReadOnlyFieldsMixin:
    task_id: PyObjectId = Field(title='Task ID')
    minion_inner_id: PyObjectId = Field(title='Minion Mongo ID')


class TaskMinionEditableFieldsMixin:
    status: TaskMinionStatus = Field(title='Status', default=TaskMinionStatus.pending)

    start_last_dt: TimezoneAwareDatetime | None = Field(title='Last job start dt', default=None)
    finished_dt: TimezoneAwareDatetime | None = Field(title='Processing finished dt', default=None)
    check_unactive_last_job_dt: TimezoneAwareDatetime | None = Field(title='Last check unactive dt', default=None)


class TaskMinionCreateSchema(BaseModel, TaskMinionReadOnlyFieldsMixin, TaskMinionEditableFieldsMixin): ...


class TaskMinionUpdateSchema(BaseModel, TaskMinionEditableFieldsMixin):
    model_config = ConfigDict(extra='ignore')


class TaskMinionJoinedFieldsMixin:
    minion_id: str = Field(title='Minion ID')
    master: str = Field(title='Master')
    last_activity: TimezoneAwareDatetime | None = Field(title='Last activity', default=None)
    jobs: dict[str, JobReturnStatus] = Field(title='Jobs', default={})
    count_runs: int = Field(title='Count runs')


class TaskMinionModel(
    BaseModel,
    TaskMinionJoinedFieldsMixin,
    CreatedModifiedMixin,
    TaskMinionReadOnlyFieldsMixin,
    TaskMinionEditableFieldsMixin,
    IDMixin,
): ...


class TaskMinionInnerIdOnly(BaseModel, IDMixin):
    task_id: PyObjectId = Field(title='Task ID')
    minion_inner_id: PyObjectId = Field(title='Minion Mongo ID')


# REST


class TaskMinionListBody(SkipLimitParams, QueryParams, SortParams):
    model_config = ConfigDict(
        extra='ignore',
    )
