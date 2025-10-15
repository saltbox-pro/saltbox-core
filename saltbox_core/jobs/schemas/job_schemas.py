from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PastDatetime,
    computed_field,
    field_validator,
    model_validator,
)
from pydantic.functional_validators import AfterValidator

from saltbox_bridge_messages import SaltTgtType
from saltbox_core.utilities.jid import JID, JidError
from saltbox_core.utilities.salt import fill_salt_kwarg_from_arg
from saltbox_sdk.db.mongo.schemas_base import IDMixin
from saltbox_sdk.db.schemas_base import SYSTEM_SHORT_USER, CreatedModifiedMixin, SkipLimitParams, Source, UserShort


def jidable[JID_T: str | int](value: JID_T) -> JID_T:
    try:
        JID(value)
    except JidError as err:
        raise ValueError(err) from err
    return value


StrJid = Annotated[str, AfterValidator(jidable)]


# Jobs


class JobStatus(StrEnum):
    in_queue = 'in_queue'
    started = 'started'
    waiting_returns = 'waiting_returns'
    finished = 'finished'


class JobReadOnlyFieldsMixin:
    tgt: str | list[str]
    tgt_type: SaltTgtType
    salt_master: str
    system_user: str | None = None
    fun: str
    arg: list | None = None
    kwarg: dict | None = None

    user: UserShort | None = Field(default=SYSTEM_SHORT_USER)
    source: Source | None = None


class JobEditableFieldsMixin:
    minions: list[str] = Field(default=[])
    missing: list[str] = Field(default=[])
    returning: dict[str, bool | None] = Field(default={})
    stamp: str | None = Field(default=None)
    status: JobStatus = JobStatus.in_queue


class JobComputedFieldsMixin:
    @computed_field(title='Timestamp decoded from JID')
    def fms_jid_timestamp(self) -> Annotated[datetime, PastDatetime]:
        return JID(self.jid).to_datetime()  # type: ignore


class JobCreateSchema(BaseModel, JobReadOnlyFieldsMixin, JobEditableFieldsMixin):
    jid: StrJid | None = Field(default=None)

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
    BaseModel, CreatedModifiedMixin, JobReadOnlyFieldsMixin, JobEditableFieldsMixin, JobComputedFieldsMixin, IDMixin
):
    jid: StrJid


# Rest


class StartEndDatetimeMixin(BaseModel):
    start_datetime: Annotated[datetime, PastDatetime]
    end_datetime: datetime

    @field_validator('start_datetime', 'end_datetime', mode='before')
    @classmethod
    def forbid_year_only(cls, v: Any) -> datetime:
        if isinstance(v, str) and v.isdigit():
            msg = '`start_datetime` and `end_datetime` must be in full datetime format (YYYY-MM-DD)'
            raise ValueError(msg)
        return datetime.fromisoformat(v) if isinstance(v, str) else v

    @model_validator(mode='after')
    def dt_validate(self) -> 'StartEndDatetimeMixin':
        if self.start_datetime > self.end_datetime:
            msg = '`end_datetime` must be before `start_datetime`'
            raise ValueError(msg)

        return self


class JobsListRequest(SkipLimitParams, StartEndDatetimeMixin):
    desc: bool = True


class JobsListResponse(BaseModel):
    jid: str
    tgt: str | list[str]
    tgt_type: str
    salt_master: str
    fun: str
    user: UserShort | None = Field(default=SYSTEM_SHORT_USER)
    system_user: str | None = None

    @computed_field(title='Timestamp decoded from JID')
    def fms_jid_timestamp(self) -> Annotated[datetime, PastDatetime]:
        return JID(self.jid).to_datetime()


class CreateJobRequest(BaseModel):
    tgt: str | list[str] = '*'
    tgt_type: SaltTgtType = 'glob'
    fun: str = 'test.ping'
    salt_master: str = 'salt-master'
    arg: list | None = None
    kwarg: dict | None = None


# Permissions


class JobsActions(StrEnum):
    CREATE = 'create'
    READ = 'read'
    LIST = 'list'
    RUN = 'run'
