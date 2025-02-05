import logging.config
from datetime import datetime
from enum import Enum
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from fastms_core.config import LOG_CONFIG
from fastms_core.db.mongo.schemas_base import CreatedModifiedMixin, IDMixin, PaginatedListParams, PyObjectId
from fastms_core.utilities.helpers import get_now_stamp_str

logging.config.dictConfig(LOG_CONFIG.model_dump())

logger = logging.getLogger(__name__)


class TaskTgtType(str, Enum):
    minions_collection = 'minions_collection'
    minions_list = 'minions_list'


class TaskJobStatus(str, Enum):
    running = 'running'
    succeeded = 'succeeded'
    failed = 'failed'


class TaskJobReturnStatus(str, Enum):
    succeeded = 'succeeded'
    failed = 'failed'
    waiting = 'waiting'
    timeout = 'timeout'


class TaskJobTarget(BaseModel):
    tgt: str = Field(title='Salt tgt')
    master: str = Field(title='Master')


class TaskJob(BaseModel):
    jid: str = Field(title='JID')
    target: TaskJobTarget = Field(title='Job salt target')
    status: TaskJobStatus = Field(title='Job status', default=TaskJobStatus.running)
    returns_statuses: dict[str, TaskJobReturnStatus] = Field(title='Job returns statuses by minions', default={})

    created_stamp: str = Field(title='Created stamp', default_factory=get_now_stamp_str)
    finished_stamp: str | None = Field(title='Finished stamp', default=None)


class TaskStatus(str, Enum):
    created = 'created'
    running = 'running'
    finished = 'finished'
    stopped = 'stopped'


class TaskReadOnlyFieldsMixin:
    status: TaskStatus = Field(title='Status', default=TaskStatus.created)

    run_dt: datetime | None = Field(title='Run datetime', default=None)
    stopped_dt: datetime | None = Field(title='Stopped datetime', default=None)
    finished_dt: datetime | None = Field(title='Finished datetime', default=None)

    targets_queue: list[TaskJobTarget] | None = Field(title='Jobs queue', default=None)
    jobs: list[TaskJob] = Field(title='Jobs', default=[])
    minions_retries_counts: dict[str, int] = Field(title='Minions retries cunts', default={})
    failed_for_minions: list[str] = Field(title='Minions failed', default=[])


class TaskEditableFieldsMixin:
    task_template_id: PyObjectId | None = Field(title='Task template')
    # collection_id: PyObjectId | None = Field(title='Collection template')
    fun: str = Field(title='Salt fun')
    task_args: list[str] = Field(title='Args')
    task_kwargs: dict[str, Any] = Field(title='Kwargs')

    tgt_type: TaskTgtType = Field(title='Targeting type')
    tgt_value: str = Field(title='Targeting value')
    batch_size: int | None = Field(title='Batch size', default=None)
    max_retries: int = Field(title='Max retries', default=3)


class TaskCreateSchema(BaseModel, TaskEditableFieldsMixin, TaskReadOnlyFieldsMixin):
    pass


class TaskUpdateSchema(BaseModel, TaskEditableFieldsMixin):
    model_config = ConfigDict(
        extra='forbid',
    )

class TaskForceUpdateSchema(BaseModel, TaskEditableFieldsMixin, TaskReadOnlyFieldsMixin):
    pass


class TaskModel(
    BaseModel, CreatedModifiedMixin, TaskEditableFieldsMixin, TaskReadOnlyFieldsMixin, IDMixin
):
    pass


class TaskCreateFromTemplateSchema(BaseModel):
    task_template_id: PyObjectId = Field(title='Task template id')
    variables_data: dict[str, Any] = Field(title='Variables data')
    tgt_type: TaskTgtType = Field(title='Targeting type')
    tgt_value: str | PyObjectId = Field(title='Targeting value')
    batch_size: int | None = Field(title='Batch size', default=None)
    max_retries: int = Field(title='Max retries', default=3)

    @model_validator(mode='after')
    def validation_targeting(self) -> 'TaskCreateFromTemplateSchema':
        if self.tgt_type == TaskTgtType.minions_list:
            if not isinstance(self.tgt_value, str):
                msg: str = 'For task with type "minions_list" value of "tgt_value" must be a string'
                raise ValueError(msg)

            if not len(self.tgt_value):
                msg = '"tgt_value" must not be empty'
                raise ValueError(msg)

            if '*' in self.tgt_value.split(','):
                msg = '"tgt_value" must not contain "*"'
                raise ValueError(msg)

        return self


class TaskListResponseSchema(TaskModel):
    targets_queue: Any = Field(exclude=True)
    jobs: Any = Field(exclude=True)
    minions_retries_counts: Any = Field(exclude=True)
    failed_for_minions: Any = Field(exclude=True)


class TaskListQueryParams(PaginatedListParams):
    model_config: ClassVar[ConfigDict] = {'extra': 'forbid'}
