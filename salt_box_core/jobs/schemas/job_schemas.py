from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Self, TypeVar, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PastDatetime,
    computed_field,
    model_validator,
)
from pydantic.functional_validators import AfterValidator

from salt_box_core.utilities.jid import JID, JidError
from salt_box_core.utilities.salt import fill_salt_kwarg_from_arg

T = TypeVar('T')
JID_T = TypeVar('JID_T', str, int)


def jidable(value: JID_T) -> JID_T:
    try:
        JID(value)
    except JidError as err:
        raise ValueError(err) from err
    return value


IntJid = Annotated[int, AfterValidator(jidable)]
StrJid = Annotated[str, AfterValidator(jidable)]


class NullObj(BaseModel):
    model_config = ConfigDict(extra='forbid')


class JobData(BaseModel):  # type: ignore[no-redef]
    data_args: list | None = Field(alias='args', default=None)
    data_kwargs: dict | None = Field(alias='kwargs', default=None)


class Job(BaseModel):
    class JobStatus(str, Enum):
        in_queue = 'in_queue'
        started = 'started'

    jid: StrJid
    tgt: str | list[str]
    tgt_type: str
    user: str | None = None
    fun: str
    arg: list | None = None
    kwarg: dict | None = None
    minions: list[str] = []
    missing: list[str] = []
    stamp: str | None = Field(alias='_stamp', default=None)
    status: JobStatus

    @computed_field(title='Timestamp decoded from JID')
    def fms_jid_timestamp(self) -> Annotated[datetime, PastDatetime]:
        return JID(self.jid).to_datetime()

    @model_validator(mode='before')
    @classmethod
    def _extract_kwargs(cls, data: T) -> T:
        # data may be an instantiated Job or potentially any object
        if not isinstance(data, dict):
            return data

        data['arg'], data['kwarg'] = fill_salt_kwarg_from_arg(data.get('arg'), data.get('kwarg'))

        return cast(T, data)


class JobCreate(BaseModel):
    tgt: str
    tgt_type: str
    fun: str
    data: JobData | None = None
    jid: str | None = None
    jid_postfix: str | None = None
    salt_master: str | None = None


class JobResult(BaseModel):
    """
    Describes return data for a job
    """

    # Officially obligatory fields are only [ id, jid, retcode, fun, return ]
    # https://docs.saltproject.io/en/latest/topics/event/master_events.html#job-events
    model_config = ConfigDict(extra='allow')

    id: str
    success: bool
    salt_master: str
    return_: Any = Field(alias='return')
    retcode: int
    jid: StrJid
    fun: str
    fun_args: list | None = None
    fun_kwarg: dict | None = None
    user: str
    stamp: str = Field(alias='_stamp')

    @model_validator(mode='before')
    @classmethod
    def _extract_kwargs(cls, data: T) -> T:
        # data may be an instantiated Job or potentially any object
        if not isinstance(data, dict):
            return data

        data['fun_args'], data['fun_kwarg'] = fill_salt_kwarg_from_arg(data.get('fun_args'), data.get('fun_kwarg'))

        return cast(T, data)


class PubData(BaseModel):
    """Salt LocalClient.run_job response representation"""

    jid: StrJid
    minions: list[str] = Field(min_length=1)


class JobsListRequest(BaseModel):
    start_datetime: Annotated[datetime, PastDatetime]
    end_datetime: datetime | None = None

    @model_validator(mode='after')
    def dt_validate(self) -> Self:
        if self.end_datetime and self.start_datetime > self.end_datetime:
            msg = '`end_datetime` must be before `start_datetime`'
            raise ValueError(msg)

        return self


class CreateJobResponse(BaseModel):
    jid: StrJid


class CreateJobRequest(BaseModel):
    tgt: str = '*'
    tgt_type: str = 'glob'
    fun: str = 'test.ping'
    salt_master: str = 'salt-master'
    data: JobData | None = None


class GetJobReturnResponse(BaseModel):
    result: list[JobResult]
    cursor: int = Field(description='Pointer to get next portion of data, 0 when no more data')
    length: int
