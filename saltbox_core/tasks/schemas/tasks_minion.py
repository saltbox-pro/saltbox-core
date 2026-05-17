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


class TaskMinionReadOnlyFieldsMixin(BaseModel):
    task_id: PyObjectId = Field(title='Task ID')
    minion_inner_id: PyObjectId = Field(title='Minion Mongo ID')


class TaskMinionEditableFieldsMixin(BaseModel):
    status: TaskMinionStatus = Field(title='Status', default=TaskMinionStatus.pending)

    start_last_dt: TimezoneAwareDatetime | None = Field(title='Last job start dt', default=None)
    finished_dt: TimezoneAwareDatetime | None = Field(title='Processing finished dt', default=None)
    check_unactive_last_job_dt: TimezoneAwareDatetime | None = Field(title='Last check unactive dt', default=None)


class TaskMinionCreateSchema(TaskMinionReadOnlyFieldsMixin, TaskMinionEditableFieldsMixin): ...


class TaskMinionUpdateSchema(TaskMinionEditableFieldsMixin):
    model_config = ConfigDict(extra='ignore')


class TaskMinionJoinedFieldsMixin(BaseModel):
    minion_id: str = Field(title='Minion ID')
    master: str = Field(title='Master')
    last_activity: TimezoneAwareDatetime | None = Field(title='Last activity', default=None)
    jobs: dict[str, JobReturnStatus] = Field(title='Jobs', default={})
    count_runs: int = Field(title='Count runs')


class TaskMinionModel(
    TaskMinionJoinedFieldsMixin,
    CreatedModifiedMixin,
    TaskMinionReadOnlyFieldsMixin,
    TaskMinionEditableFieldsMixin,
    IDMixin,
): ...


# System


class TaskMinionInnerIdOnly(IDMixin):
    task_id: PyObjectId = Field(title='Task ID')
    minion_inner_id: PyObjectId = Field(title='Minion Mongo ID')


class TaskMinionTgtOnlySchema(IDMixin):
    minion_id: str = Field(title='Minion ID')
    master: str = Field(title='Master')


class TaskMinionForTaskStatusUpdateSchema(IDMixin):
    count_runs: int = Field(title='Count runs')


# REST


class TaskMinionListBody(SkipLimitParams, QueryParams, SortParams):
    model_config = ConfigDict(
        extra='ignore',
    )


class TaskMinionListResponse(CreatedModifiedMixin, IDMixin):
    minion_inner_id: PyObjectId = Field(title='Minion Mongo ID')
    status: TaskMinionStatus = Field(title='Status', default=TaskMinionStatus.pending)
    start_last_dt: TimezoneAwareDatetime | None = Field(title='Last job start dt', default=None)
    finished_dt: TimezoneAwareDatetime | None = Field(title='Processing finished dt', default=None)

    # Joined fields
    minion_id: str = Field(title='Minion ID')
    master: str = Field(title='Master')
    count_runs: int = Field(title='Count runs')
