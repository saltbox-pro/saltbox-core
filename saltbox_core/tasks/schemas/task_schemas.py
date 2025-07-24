from enum import StrEnum
from typing import Any, ClassVar, Self

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from saltbox_core.db.schemas_base import UserShort
from saltbox_sdk.db.mongo.schemas_base import IDMixin, PyObjectId
from saltbox_sdk.db.schemas_base import CreatedModifiedMixin, SkipLimitParams
from saltbox_sdk.utilities.helpers import Iso8601ZDatetime as TimezoneAwareDatetime
from saltbox_sdk.utilities.helpers import utc_now

# Task job


class TaskJobStatus(StrEnum):
    pending = 'pending'
    running = 'running'
    succeeded = 'succeeded'
    failed = 'failed'


class TaskJobReturnStatus(StrEnum):
    succeeded = 'succeeded'
    failed = 'failed'
    waiting = 'waiting'
    timeout = 'timeout'


class TaskJobTargetType(StrEnum):
    list = 'list'
    compound = 'compound'


class TaskJobTarget(BaseModel):
    tgt: str = Field(title='Salt tgt')
    tgt_type: TaskJobTargetType = Field(title='Salt tgt type')
    master: str = Field(title='Master')


class TaskJob(BaseModel):
    jid: str = Field(title='JID')
    target: TaskJobTarget = Field(title='Job salt target')
    status: TaskJobStatus = Field(title='Job status', default=TaskJobStatus.pending)
    returns_statuses: dict[str, TaskJobReturnStatus] = Field(title='Job returns statuses by minions', default={})

    minions_by_targeting: list[str] = Field(title='List of minions ids by targeting')
    minions_from_salt: list[str] | None = Field(title='Computed minions by salt', default=None)

    created_dt: TimezoneAwareDatetime = Field(title='Created stamp', default_factory=utc_now)
    finished_dt: TimezoneAwareDatetime | None = Field(title='Finished stamp', default=None)


# Task minion


class TaskTargetMinion(BaseModel):
    minion_id: str
    master: str


class TaskMinionStatus(StrEnum):
    pending = 'pending'
    in_work = 'in_work'
    success = 'success'
    failed = 'failed'


class TaskMinionJobStatus(StrEnum):
    created = 'created'
    in_work = 'in_work'
    success = 'success'
    failed = 'failed'
    ignored = 'ignored'


class TaskMinion(BaseModel):
    id: PyObjectId | None = Field(title='Minion id', default=None)
    minion_id: str
    master: str

    status: TaskMinionStatus = Field(title='status', default=TaskMinionStatus.pending)

    jobs: dict[str, TaskMinionJobStatus] = Field(title='Jobs', default={})

    start_last_dt: TimezoneAwareDatetime | None = Field(title='Last job start dt', default=None)
    finished_dt: TimezoneAwareDatetime | None = Field(title='Processing finished dt', default=None)

    @computed_field(title='Count job runs')
    def count_runs(self) -> int:
        return len(self.jobs)


# Task postprocessing


class TaskPostProcessingType(StrEnum):
    on_success = 'on_success'
    on_anyway = 'on_anyway'


class TaskPostProcessingMinionForWait(BaseModel):
    minion_id: str = Field(title='Minion ID')
    master: str = Field(title='Master')


class TaskPostProcessingCreate(BaseModel):
    type: TaskPostProcessingType = Field(title='Postprocessing type')

    wait_minions: list[TaskPostProcessingMinionForWait] = Field(title='Wait minions', default=[])
    wait_minions_ttl: int = Field(title='Wait minions TTL', ge=1, default=60 * 5)

    task_create_request: 'TaskCreateRequestSchema | None' = Field(title='Create task', default=None)

    notify: bool = Field(title='Notify', default=False)


class TaskPostProcessing(TaskPostProcessingCreate):
    task_create_id: PyObjectId | None = Field(title='Task ID', default=None)
    notify_dt: TimezoneAwareDatetime | None = Field(title='Notify dt', default=None)


# Task


class TaskStatus(StrEnum):
    created = 'created'
    running = 'running'
    stopping = 'stopping'
    stopped = 'stopped'
    postprocessing = 'postprocessing'
    finished = 'finished'


class TaskData(BaseModel):  # type: ignore[no-redef]
    args: list | None = Field(default=None)
    kwargs: dict | None = Field(default=None)


class TaskTemplateShort(BaseModel):
    id: PyObjectId
    title: str
    name: str
    repo_id: PyObjectId
    commit_hash: str


class CollectionShort(BaseModel):
    id: PyObjectId
    slug: str
    title: str


class TaskReadOnlyFieldsMixin:
    parent_task_id: PyObjectId | None = Field(title='Parent task id', default=None)
    task_template: TaskTemplateShort | None = Field(title='Task template', default=None)

    fun: str = Field(title='Salt fun')
    task_args: list[str] | None = Field(title='Args', default=None)
    task_kwargs: dict[str, Any] | None = Field(title='Kwargs', default=None)

    target_collection: CollectionShort = Field(title='Target collection')
    target_query: dict[str, Any] = Field(title='Target query', default={})
    target_minions: list[TaskTargetMinion] = Field(title='Target minions', default=[])
    target_masters: list[str] = Field(title='Target masters', default=[])

    batch_size: int | None = Field(title='Batch size', default=None)
    max_jobs_count_at_same_time: int = Field(title='Max jobs count at some time', ge=1, default=1)
    max_retries: int = Field(title='Max retries', ge=1, default=3)

    user: UserShort


class TaskEditableFieldsMixinPart:
    status: TaskStatus = Field(title='Status', default=TaskStatus.created)

    run_dt: TimezoneAwareDatetime | None = Field(title='Run datetime', default=None)
    stopped_dt: TimezoneAwareDatetime | None = Field(title='Stopped datetime', default=None)
    postprocessing_dt: TimezoneAwareDatetime | None = Field(title='Postprocessing datetime', default=None)
    finished_dt: TimezoneAwareDatetime | None = Field(title='Finished datetime', default=None)


class TaskEditableFieldsMixin(TaskEditableFieldsMixinPart):
    jobs: dict[str, TaskJob] = Field(title='Jobs', default={})
    minions: dict[str, TaskMinion] = Field(title='Minions failed', default={})

    postprocessing: TaskPostProcessing | None = Field(title='Postprocessing', default=None)


class TaskCreateSchema(BaseModel, TaskEditableFieldsMixin, TaskReadOnlyFieldsMixin):
    pass


class TaskUpdateSchema(BaseModel, TaskEditableFieldsMixin):
    model_config = ConfigDict(
        extra='ignore',
    )


class TaskModel(BaseModel, CreatedModifiedMixin, TaskEditableFieldsMixin, TaskReadOnlyFieldsMixin, IDMixin):
    pass


class TaskCreateRequestSchema(BaseModel):
    task_template_id: PyObjectId | None = Field(title='Task template id', default=None)
    fun: str | None = Field(title='Salt fun', default=None)

    salt_masters: list[str] = ['salt-master']
    data: TaskData | None = None

    collection_id: PyObjectId = Field(title='Collection id')
    query: dict = Field(title='Query', default={})
    minions: list[TaskTargetMinion] = Field(title='Minions', default=[])

    batch_size: int | None = Field(title='Batch size', default=None)
    max_jobs_count_at_same_time: int = Field(title='Max jobs count at some time', ge=1, default=1)
    max_retries: int = Field(title='Max retries', default=3)

    postprocessing: TaskPostProcessingCreate | None = Field(title='Postprocessing', default=None)
    user: UserShort = Field(title='User', default_factory=lambda: UserShort(sub='', name='Unknown', email=''))

    @model_validator(mode='after')
    def validate_local_path(self) -> Self:
        if self.task_template_id is None and self.fun is None:
            msg = 'One of `task_template` or `fun` must be set'
            raise ValueError(msg)

        if self.task_template_id is not None and self.fun is not None:
            msg = 'Only one of `task_template` or `fun` can be set'
            raise ValueError(msg)

        return self


class TaskCreateInputSchema(TaskCreateRequestSchema):
    # user: UserShort
    parent_task_id: PyObjectId | None = Field(title='Parent task id', default=None)


class TaskListResponseSchema(
    BaseModel, CreatedModifiedMixin, TaskEditableFieldsMixinPart, TaskReadOnlyFieldsMixin, IDMixin
):
    pass


class TaskListQueryParams(SkipLimitParams):
    collection_slug: str
    model_config: ClassVar[ConfigDict] = {'extra': 'forbid'}
