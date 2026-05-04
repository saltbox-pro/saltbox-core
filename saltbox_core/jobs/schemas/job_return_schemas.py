from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from saltbox_core.jobs.schemas.job_schemas import StrJid
from saltbox_core.utilities.salt import fill_salt_kwarg_from_arg
from saltbox_sdk.db.mongo.schemas_base import IDMixin, QueryParams, SortParams
from saltbox_sdk.db.schemas_base import SYSTEM_SHORT_USER, CreatedModifiedMixin, SkipLimitParams, Source, UserShort
from saltbox_sdk.utilities.helpers import Iso8601ZDatetime as TimezoneAwareDatetime

# Job returns


class JobReturnStatus(StrEnum):
    waiting = 'waiting'
    success = 'success'
    failed = 'failed'
    timeout = 'timeout'
    ignored = 'ignored'


class JobReturnReadOnlyFieldsMixin:
    minion_id: str
    salt_master: str
    jid: StrJid
    fun: str
    user: UserShort | None = Field(default=SYSTEM_SHORT_USER)
    source: Source | None = None


class JobReturnEditableFieldsMixin:
    status: JobReturnStatus = Field(default=JobReturnStatus.waiting)
    retcode: int | None = None
    fun_args: list | None = None
    fun_kwarg: dict | None = None
    system_user: str | None = None
    stamp: TimezoneAwareDatetime | None = None
    stamp_job: TimezoneAwareDatetime | None = Field(default=None)


class JobReturnAggregatedFieldsMixin:
    success: bool | None = None


class JobReturnCreateSchema(BaseModel, JobReturnReadOnlyFieldsMixin, JobReturnEditableFieldsMixin):
    model_config = ConfigDict(extra='ignore')

    @model_validator(mode='before')
    @classmethod
    def _extract_kwargs[T](cls, data: T) -> T:
        # data may be an instantiated Job or potentially any object
        if not isinstance(data, dict):
            return data

        data['fun_args'], data['fun_kwarg'] = fill_salt_kwarg_from_arg(data.get('fun_args'), data.get('fun_kwarg'))

        return data


class JobReturnUpdateSchema(BaseModel, JobReturnEditableFieldsMixin):
    model_config = ConfigDict(extra='ignore')


class JobReturnDataMixin:
    data: Any = Field(default=None)


class JobReturnModel(
    BaseModel,
    JobReturnAggregatedFieldsMixin,
    CreatedModifiedMixin,
    JobReturnReadOnlyFieldsMixin,
    JobReturnEditableFieldsMixin,
    JobReturnDataMixin,
    IDMixin,
): ...


# REST


class JobReturnsListBody(SkipLimitParams, QueryParams, SortParams):
    model_config = ConfigDict(extra='ignore')


class JobReturnDataOnlyScheme(BaseModel, JobReturnDataMixin, IDMixin):
    jid: StrJid
    minion_id: str
    salt_master: str


class JobReturnListResponse(
    BaseModel,
    JobReturnAggregatedFieldsMixin,
    CreatedModifiedMixin,
    JobReturnReadOnlyFieldsMixin,
    JobReturnEditableFieldsMixin,
    IDMixin,
): ...
