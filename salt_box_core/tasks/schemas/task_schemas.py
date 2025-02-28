import logging.config
from datetime import datetime
from enum import Enum
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, computed_field

from salt_box_core.config import LOG_CONFIG
from salt_box_core.db.mongo.schemas_base import (
    CreatedModifiedMixin,
    IDMixin,
    PaginatedListParams,
    PyObjectId,
    UserShort,
)
from salt_box_core.utilities.helpers import utc_now

logging.config.dictConfig(LOG_CONFIG.model_dump())

logger = logging.getLogger(__name__)


# Task job


class TaskJobStatus(str, Enum):
    pending = 'pending'
    running = 'running'
    succeeded = 'succeeded'
    failed = 'failed'


class TaskJobReturnStatus(str, Enum):
    succeeded = 'succeeded'
    failed = 'failed'
    waiting = 'waiting'
    timeout = 'timeout'


class TaskJobTargetType(str, Enum):
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

    created_dt: datetime = Field(title='Created stamp', default_factory=utc_now)
    finished_dt: datetime | None = Field(title='Finished stamp', default=None)


# Task minion


class TaskMinionStatus(str, Enum):
    pending = 'pending'
    in_work = 'in_work'
    success = 'success'
    failed = 'failed'


class TaskMinionJobStatus(str, Enum):
    created = 'created'
    in_work = 'in_work'
    success = 'success'
    failed = 'failed'
    ignored = 'ignored'


class TaskMinion(BaseModel):
    minion_id: str
    master: str

    status: TaskMinionStatus = Field(title='status', default=TaskMinionStatus.pending)

    jobs: dict[str, TaskMinionJobStatus] = Field(title='Jobs', default={})

    start_last_dt: datetime | None = Field(title='Last job start dt', default=None)
    finished_dt: datetime | None = Field(title='Processing finished dt', default=None)

    @computed_field(title='Count job runs')
    def count_runs(self) -> int:
        return len(self.jobs)


# Task


class TaskStatus(str, Enum):
    created = 'created'
    running = 'running'
    finished = 'finished'
    stopping = 'stopping'
    stopped = 'stopped'


class TaskData(BaseModel):  # type: ignore[no-redef]
    data_args: list | None = Field(alias='args', default=None)
    data_kwargs: dict | None = Field(alias='kwargs', default=None)


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
    task_template: TaskTemplateShort = Field(title='Task template')

    fun: str = Field(title='Salt fun')
    task_args: list[str] = Field(title='Args')
    task_kwargs: dict[str, Any] = Field(title='Kwargs')

    target_collection: CollectionShort = Field(title='Target collection')
    target_query: dict[str, Any] = Field(title='Target query', default={})
    target_minions: list[PyObjectId] = Field(title='Target minions', default=[])
    target_masters: list[str] = Field(title='Target masters', default=[])

    # batch_size: int = Field(title='Batch size', ge=1, le=10000, default=1000)
    batch_size: int | None = Field(title='Batch size', default=None)
    max_jobs_count_at_same_time: int = Field(title='Max jobs count at some time', ge=1, default=1)
    max_retries: int = Field(title='Max retries', ge=1, default=3)

    user: UserShort


class TaskEditableFieldsMixin:
    status: TaskStatus = Field(title='Status', default=TaskStatus.created)

    run_dt: datetime | None = Field(title='Run datetime', default=None)
    stopped_dt: datetime | None = Field(title='Stopped datetime', default=None)
    finished_dt: datetime | None = Field(title='Finished datetime', default=None)

    jobs: dict[str, TaskJob] = Field(title='Jobs', default={})
    minions: dict[str, TaskMinion] = Field(title='Minions failed', default={})


class TaskCreateSchema(BaseModel, TaskEditableFieldsMixin, TaskReadOnlyFieldsMixin):
    pass


class TaskUpdateSchema(BaseModel, TaskEditableFieldsMixin):
    model_config = ConfigDict(
        extra='ignore',
    )


class TaskModel(BaseModel, CreatedModifiedMixin, TaskEditableFieldsMixin, TaskReadOnlyFieldsMixin, IDMixin):
    pass


class TaskCreateRequestSchema(BaseModel):
    task_template_id: PyObjectId = Field(title='Task template id')
    salt_masters: list[str] = ['salt-master']
    data: TaskData | None = None

    collection_id: PyObjectId = Field(title='Collection')
    query: dict = Field(title='Query', default={})
    minions: list[PyObjectId] = Field(title='Minions', default=[])

    batch_size: int | None = Field(title='Batch size', default=None)
    max_retries: int = Field(title='Max retries', default=3)


class TaskCreateFromTemplateSchema(TaskCreateRequestSchema):
    user: UserShort


class TaskListResponseSchema(TaskModel):
    jobs: Any = Field(exclude=True)
    minions: Any = Field(exclude=True)


class TaskListQueryParams(PaginatedListParams):
    model_config: ClassVar[ConfigDict] = {'extra': 'forbid'}
