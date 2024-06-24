from typing import Any, Optional, Union

from pydantic import BaseModel, Field, PastDatetime, computed_field, conlist

from app.utilities.jid import jid_to_datetime


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
    return_: conlist(AuthItem, min_length=1) = Field(alias='return')


class Job(BaseModel):
    jid: str
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
    jid: str
    fun: str
    fun_args: Optional[list] = None
    fun_kwarg: Optional[dict] = None
    user: str
    stamp: str = Field(alias='_stamp')


class PubData(BaseModel):
    """ Salt LocalClient.run_job response representation """
    jid: int
    minions: conlist(str, min_length=1)


class CreateJobResponse(BaseModel):
    return_: conlist(Union[PubData, NullObj], min_length=1) = Field(alias='return')


class CreateJobRequest(BaseModel):
    tgt: str = '*'
    tgt_type: str = 'glob'
    fun: str = 'test.ping'
    arg: list = []
    kwarg: dict = {}
