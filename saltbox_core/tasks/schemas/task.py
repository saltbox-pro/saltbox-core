from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from saltbox_core.config import SETTINGS
from saltbox_core.tasks.schemas.tasks_status import TaskStatus
from saltbox_core.tasks.schemas.tasks_template import TaskTemplateDefaultsSchema
from saltbox_sdk.db.mongo.schemas_base import IDMixin, PyObjectId, QueryParams, SortParams
from saltbox_sdk.db.schemas_base import CreatedModifiedMixin, SkipLimitParams, SourceMixin, UserShort
from saltbox_sdk.exceptions import SaltBoxValidationException
from saltbox_sdk.utilities.helpers import Iso8601ZDatetime as TimezoneAwareDatetime
from saltbox_sdk.utilities.helpers import utc_now

# Task


class TaskType(StrEnum):
    classic = 'classic'
    policy = 'policy'


class TaskTemplateShort(IDMixin):
    title: str = Field(title='Template title')
    name: str = Field(title='Template name')
    repo_id: PyObjectId | None = Field(title='Repository id', default=None)
    commit_hash: str | None = Field(title='Repository commit hash', default=None)
    defaults: TaskTemplateDefaultsSchema | None = Field(title='Default values', default=None)


class CollectionShort(IDMixin):
    slug: str = Field(title='Collection slug')
    title: str = Field(title='Collection title')


class TaskStatusShort(CreatedModifiedMixin):
    type: TaskStatus = Field(title='Status')
    data: dict = Field(title='Status data', default_factory=dict)


class TaskReadOnlyFieldsMixin(SourceMixin):
    task_type: TaskType = Field(title='Task type')

    target_collection_id: PyObjectId = Field(title='Target ID')
    target_query: dict[str, Any] = Field(title='Target query', default={})

    task_template_id: PyObjectId | None = Field(title='Task template id', default=None)

    fun: str = Field(title='Salt fun')
    arg: list[str] | None = Field(title='Arg', default=None)
    kwarg: dict[str, Any] | None = Field(title='Kwarg', default=None)

    user: UserShort


class TaskEditableFieldsMixin(BaseModel):
    batch_size: int = Field(title='Batch size', ge=0, default=SETTINGS.tasks_defaults_batch_size)
    max_jobs_count_at_same_time: int = Field(
        title='Max jobs count at some time', ge=1, default=SETTINGS.tasks_defaults_max_jobs_count_at_same_time
    )

    max_retries: int = Field(title='Max retries', ge=0, default=SETTINGS.tasks_defaults_max_retries)
    retry_delay: int = Field(
        title='Retry delay', description='in seconds', ge=0, default=SETTINGS.tasks_defaults_retry_delay
    )
    ttl: int | None = Field(ge=0, le=SETTINGS.jobs_max_ttl, default=None)

    last_sync_dt: TimezoneAwareDatetime | None = Field(title='Last sync datetime', default=None)


class TaskTemplateJoinedFieldsMixin(BaseModel):
    task_template: TaskTemplateShort | None = Field(title='Task template', default=None)


class TaskTargetCollectionJoinedFieldsMixin(BaseModel):
    target_collection: CollectionShort = Field(title='Target collection')


class TaskStatusJoinedFieldsMixin(BaseModel):
    status: TaskStatusShort = Field(
        title='Status', default=TaskStatusShort(type=TaskStatus.created, created=utc_now(), modified=utc_now())
    )


class TaskJobJoinedFieldsMixin[TaskJobJoinedSchema: BaseModel](BaseModel):
    jobs: list[TaskJobJoinedSchema] = Field(title='Jobs', default=[])


class TaskMinionsCountAggregation(BaseModel):
    total: int = Field(title='Total number of minions', default=0)
    pending: int = Field(title='Pending minions', default=0)
    busy: int = Field(title='Busy', default=0)
    in_work: int = Field(title='In work', default=0)
    success: int = Field(title='Success', default=0)
    failed: int = Field(title='Failed', default=0)


class TaskAggregatedFieldsMixin(BaseModel):
    minions_count: TaskMinionsCountAggregation = Field()
    pillars: dict[str, JsonValue] = Field(title='Pillars', default_factory=dict)


class TaskComputedFieldsMixin(BaseModel): ...


class TaskCreateSchema(TaskEditableFieldsMixin, TaskReadOnlyFieldsMixin): ...


class TaskUpdateSchema(TaskEditableFieldsMixin):
    status: TaskStatus | None = Field(title='Status', default=None, exclude=True)

    model_config = ConfigDict(
        extra='ignore',
    )


class TaskModel(
    CreatedModifiedMixin,
    TaskTemplateJoinedFieldsMixin,
    TaskTargetCollectionJoinedFieldsMixin,
    TaskStatusJoinedFieldsMixin,
    TaskAggregatedFieldsMixin,
    TaskEditableFieldsMixin,
    TaskReadOnlyFieldsMixin,
    TaskComputedFieldsMixin,
    IDMixin,
): ...


# System


class TaskForLifespanModel(
    CreatedModifiedMixin,
    TaskTemplateJoinedFieldsMixin,
    TaskStatusJoinedFieldsMixin,
    TaskEditableFieldsMixin,
    TaskReadOnlyFieldsMixin,
    IDMixin,
): ...


class TaskForStatusUpdateSchema(IDMixin):
    max_retries: int = Field(title='Max retries', default=SETTINGS.tasks_defaults_max_retries)


class TaskWithStatusOnlySchema(TaskStatusJoinedFieldsMixin, IDMixin): ...


# REST


class TaskTargetMinion(BaseModel):
    minion_id: str = Field(title='Target minion ID')
    salt_master: str = Field(title='Target minion master')


class TaskData(BaseModel):  # type: ignore[no-redef]
    args: list[str] | None = Field(title='Arg', default=None)
    kwargs: dict[str, Any] | None = Field(title='Kwarg', default=None)


class TaskCreateRequestSchema(BaseModel):
    task_type: TaskType = Field(title='Task type')

    collection_id: PyObjectId | None = Field(title='Collection ID', default=None)
    collection_slug: str | None = Field(title='Collection slug', default=None)
    query: dict = Field(title='Query', default={})
    minions: list[TaskTargetMinion] = Field(title='Minions', default=[])

    task_template_id: PyObjectId | None = Field(title='Task template id', default=None)

    fun: str | None = Field(title='Salt fun', default=None)
    data: TaskData | None = Field(title='Data data', default=None)

    batch_size: int | None = Field(title='Batch size', ge=0, default=None)
    max_jobs_count_at_same_time: int | None = Field(title='Max jobs count at some time', ge=1, default=None)

    max_retries: int | None = Field(title='Max retries', ge=0, default=None)
    retry_delay: int | None = Field(title='Retry delay', description='in seconds', ge=0, default=None)

    ttl: int | None = Field(ge=0, le=SETTINGS.jobs_max_ttl, default=None)
    save_pillars_as_default: bool = Field(title='Whether to save pillars as default for template', default=False)

    @model_validator(mode='after')
    def validate_fun(self) -> 'TaskCreateRequestSchema':
        if self.task_template_id is None and self.fun is None:
            msg = 'One of `task_template` or `fun` must be set'
            raise SaltBoxValidationException(msg)

        if self.task_template_id is not None and self.fun is not None:
            msg = 'Only one of `task_template` or `fun` can be set'
            raise SaltBoxValidationException(msg)

        return self

    @model_validator(mode='after')
    def validate_collection(self) -> 'TaskCreateRequestSchema':
        if self.collection_id is None and self.collection_slug is None:
            msg = 'One of `collection_id` or `collection_slug` must be set'
            raise SaltBoxValidationException(msg)

        if self.collection_id is not None and self.collection_slug is not None:
            msg = 'Only one of `collection_id` or `collection_slug` can be set'
            raise SaltBoxValidationException(msg)

        return self


class TaskCreateInputSchema(TaskCreateRequestSchema, SourceMixin):
    user: UserShort


class RestartFailedBody(BaseModel):
    minions_by_tgt: list[TaskTargetMinion] | None = Field(title='Minions by target', default=None)
    minions_by_ids: list[PyObjectId] | None = Field(title='Minions by ids', default=None)


class TaskListResponseSchema(
    CreatedModifiedMixin,
    TaskTemplateJoinedFieldsMixin,
    TaskTargetCollectionJoinedFieldsMixin,
    TaskStatusJoinedFieldsMixin,
    TaskAggregatedFieldsMixin,
    TaskEditableFieldsMixin,
    TaskReadOnlyFieldsMixin,
    TaskComputedFieldsMixin,
    IDMixin,
): ...


class TaskListBody(SkipLimitParams, QueryParams, SortParams):
    model_config = ConfigDict(extra='ignore')


# OPA


class TasksActions(StrEnum):
    CREATE = 'create'
    READ = 'read'
    LIST = 'list'
    RUN = 'run'
