from typing import Annotated, Any, Optional, Union

from pydantic import BaseModel, Field, PastDatetime, computed_field

from fastms_core.utilities.jid import jid_to_datetime, JID_REGEX

IntJid = Annotated[int, Field(gt=int(1970E+16), lt=int(1E+20))]
StrJid = Annotated[str, Field(pattern=JID_REGEX)]


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
        return jid_to_datetime(self.jid)


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
