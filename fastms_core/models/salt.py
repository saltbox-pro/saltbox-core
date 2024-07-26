from typing import cast, Annotated, Any, Optional, TypeVar, Union

from pydantic import (
    BaseModel,
    Field,
    PastDatetime,
    computed_field,
    model_validator,
)
from pydantic.functional_validators import AfterValidator

from fastms_core.utilities.jid import JID, JidError
from fastms_core.utilities.salt import fill_salt_kwarg_from_arg

T = TypeVar('T')
JID_T = TypeVar('JID_T', str, int)


def jidable(value: JID_T) -> JID_T:
    try:
        JID(value)
    except JidError as err:
        raise ValueError(err)
    return value


IntJid = Annotated[int, AfterValidator(jidable)]
StrJid = Annotated[str, AfterValidator(jidable)]


class NullObj(BaseModel):
    class Config:
        extra = 'forbid'


class AuthItem(BaseModel):
    eauth: str
    expire: float
    perms: list[str]
    start: float
    token: str
    user: str


class AuthResponse(BaseModel):
    return_: list[AuthItem] = Field(alias='return', min_length=1)


class Job(BaseModel):
    jid: StrJid
    tgt: Union[str, list[str]]
    tgt_type: str
    user: str
    fun: str
    arg: Optional[list] = None
    kwarg: Optional[dict] = None
    minions: list[str]
    stamp: str = Field(alias='_stamp')

    @computed_field(title='Timestamp decoded from JID')
    def fms_jid_timestamp(self) -> PastDatetime:
        return JID(self.jid).to_datetime()

    @model_validator(mode='before')
    @classmethod
    def _extract_kwargs(cls, data: T) -> T:
        # data may be an instantiated Job or potentially any object
        if not isinstance(data, dict):
            return data

        data['arg'], data['kwarg'] = fill_salt_kwarg_from_arg(data.get('arg'), data.get('kwarg'))

        return cast(T, data)


class JobResult(BaseModel):
    cmd: str
    id: str
    success: bool
    return_: Any = Field(alias='return')
    retcode: int
    jid: StrJid
    fun: str
    fun_args: Optional[list] = None
    fun_kwarg: Optional[dict] = None
    user: str
    stamp: str = Field(alias='_stamp')

    @model_validator(mode='before')
    @classmethod
    def _extract_kwargs(cls, data: T) -> T:
        # data may be an instantiated Job or potentially any object
        if not isinstance(data, dict):
            return data

        data['fun_args'], data['fun_kwarg'] = fill_salt_kwarg_from_arg(
            data.get('fun_args'), data.get('fun_kwarg'))

        return cast(T, data)


class PubData(BaseModel):
    """ Salt LocalClient.run_job response representation """
    jid: StrJid
    minions: list[str] = Field(min_length=1)


class CreateJobResponse(BaseModel):
    return_: list[Union[PubData, NullObj]] = Field(alias='return', min_length=1)


class CreateJobRequest(BaseModel):
    tgt: str = '*'
    tgt_type: str = 'glob'
    fun: str = 'test.ping'
    arg: list = []
    kwarg: dict = {}
