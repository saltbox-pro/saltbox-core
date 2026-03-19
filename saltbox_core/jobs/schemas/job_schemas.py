from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, PastDatetime, computed_field, model_validator
from pydantic.functional_validators import AfterValidator

from saltbox_bridge_messages import SaltTgtType
from saltbox_core.config import SETTINGS
from saltbox_core.utilities.jid import JID, JidError
from saltbox_core.utilities.salt import fill_salt_kwarg_from_arg
from saltbox_sdk.db.mongo.schemas_base import IDMixin, QueryParams, SortParams
from saltbox_sdk.db.schemas_base import SYSTEM_SHORT_USER, CreatedModifiedMixin, SkipLimitParams, Source, UserShort
from saltbox_sdk.utilities.helpers import Iso8601ZDatetime as TimezoneAwareDatetime


def jidable[JID_T: str | int](value: JID_T) -> JID_T:
    try:
        JID(value)
    except JidError as err:
        raise ValueError(err) from err
    return value


StrJid = Annotated[str, AfterValidator(jidable)]


# Jobs


class JobStatus(StrEnum):
    starting = 'starting'
    running = 'running'
    finished = 'finished'
    launch_error = 'launch_error'


class JobReadOnlyFieldsMixin:
    tgt: str | list[str]
    tgt_type: SaltTgtType
    salt_master: str
    fun: str
    arg: list | None = None
    kwarg: dict | None = None

    ttl: int = Field(ge=1, le=SETTINGS.jobs_max_ttl, default=SETTINGS.jobs_default_ttl)

    user: UserShort | None = Field(default=SYSTEM_SHORT_USER)
    source: Source | None = None


class JobEditableFieldsMixin:
    system_user: str | None = None
    minions: list[str] = Field(default=[])
    missing: list[str] = Field(default=[])
    stamp: TimezoneAwareDatetime | None = Field(default=None)
    status: JobStatus = Field(default=JobStatus.starting)
    launch_error_type: str | None = None


class JobComputedFieldsMixin:
    @computed_field(title='Timestamp decoded from JID')
    def fms_jid_timestamp(self) -> Annotated[datetime, PastDatetime]:
        return JID(self.jid).to_datetime()  # type: ignore


class JobAggregateFieldsMixin:
    returning: dict[str, bool | None] = Field(default={})
    waiting_expires_at_dt: datetime


class JobCreateSchema(BaseModel, JobReadOnlyFieldsMixin, JobEditableFieldsMixin):
    jid: StrJid | None = Field(default=None)
    ttl: int | None = Field(ge=0, le=SETTINGS.jobs_max_ttl, default=None)  # type: ignore

    model_config = ConfigDict(extra='ignore')

    @model_validator(mode='before')
    @classmethod
    def _extract_kwargs[T](cls, data: T) -> T:
        # data may be an instantiated Job or potentially any object
        if not isinstance(data, dict):
            return data

        data['arg'], data['kwarg'] = fill_salt_kwarg_from_arg(data.get('arg'), data.get('kwarg'))

        return data


class JobUpdateSchema(BaseModel, JobEditableFieldsMixin):
    jid: StrJid

    model_config = ConfigDict(extra='ignore')


class JobModel(
    BaseModel,
    CreatedModifiedMixin,
    JobReadOnlyFieldsMixin,
    JobEditableFieldsMixin,
    JobComputedFieldsMixin,
    JobAggregateFieldsMixin,
    IDMixin,
):
    jid: StrJid


class JobSimpleSchema(BaseModel, IDMixin):
    jid: StrJid
    salt_master: str
    status: JobStatus


# Rest


class JobListBody(SkipLimitParams, QueryParams, SortParams):
    model_config = ConfigDict(
        extra='ignore',
    )


class JobsListResponse(BaseModel, CreatedModifiedMixin, JobComputedFieldsMixin, IDMixin):
    jid: StrJid
    tgt: str | list[str]
    tgt_type: SaltTgtType
    salt_master: str
    system_user: str | None = None
    fun: str
    status: JobStatus
    has_failed_job_returns: bool
    launch_error_type: str | None = None

    user: UserShort | None = Field(default=SYSTEM_SHORT_USER)
    source: Source | None = None


class CreateJobRequest(BaseModel):
    tgt: str | list[str] = '*'
    tgt_type: SaltTgtType = 'glob'
    fun: str = 'test.ping'
    salt_master: str = 'salt-master'
    arg: list | None = None
    kwarg: dict | None = None
    ttl: int | None = Field(ge=0, le=SETTINGS.jobs_max_ttl, default=None)


# Permissions


class JobsActions(StrEnum):
    CREATE = 'create'
    READ = 'read'
    LIST = 'list'
    RUN = 'run'
