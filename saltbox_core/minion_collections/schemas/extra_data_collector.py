from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from saltbox_sdk.db.mongo.schemas_base import IDMixin, PyObjectId, QueryParams, SortParams
from saltbox_sdk.db.schemas_base import CreatedModifiedMixin, SkipLimitParams, UserShort


class ExtraDataCollectorLaunchType(StrEnum):
    job = 'job'
    task = 'task'
    eventbus = 'eventbus'


class ExtraDataCollectorReadOnlyFieldsMixin(BaseModel):
    namespace: str = Field(title='Namespace', examples=['inventory'])
    is_preinstalled: bool = Field(title='Is preinstalled collector', default=False)

    user: UserShort


class ExtraDataCollectorEditableFieldsMixin(BaseModel):
    description: str = Field(title='Description')
    is_enabled: bool = Field(title='Is enabled', default=True)

    launch_type: ExtraDataCollectorLaunchType = Field(title='Launch Type', default=ExtraDataCollectorLaunchType.job)
    launch_default_data: dict[str, Any] = Field(title='Launch Default Data', default={})


class ExtraDataCollectorAggregatedFieldsMixin(BaseModel):
    categories_count: int = Field(title='Categories Count', default=0)


class ExtraDataCollectorCreateSchema(ExtraDataCollectorEditableFieldsMixin, ExtraDataCollectorReadOnlyFieldsMixin):
    pass


class ExtraDataCollectorUpdateSchema(ExtraDataCollectorEditableFieldsMixin):
    model_config = ConfigDict(
        extra='forbid',
    )


class ExtraDataCollectorModel(
    IDMixin,
    CreatedModifiedMixin,
    ExtraDataCollectorEditableFieldsMixin,
    ExtraDataCollectorReadOnlyFieldsMixin,
    ExtraDataCollectorAggregatedFieldsMixin,
): ...


# REST


class ExtraDataCollectorListBody(SkipLimitParams, QueryParams, SortParams):
    model_config = ConfigDict(extra='ignore')


class ExtraDataCollectorRunBody(BaseModel):
    launch_data: dict[str, Any] = Field(title='Launch Data')

    model_config = ConfigDict(extra='ignore')


class ExtraDataCollectorCreateRequestSchema(ExtraDataCollectorEditableFieldsMixin):
    namespace: str = Field(title='Namespace', examples=['inventory'])


# OPA


class ExtraDataCollectorActions(StrEnum):
    CREATE = 'create'
    READ = 'read'
    LIST = 'list'
    RUN = 'run'
