from typing import Any, Optional, Union

from pydantic import BaseModel, Field


class Job(BaseModel):
    jid: str
    tgt: Union[str, list[str]]
    tgt_type: str
    user: str
    fun: str
    arg: Optional[list] = None
    kwarg: Optional[dict] = None
    minions: list[str]
    _stamp: str


class JobResult(BaseModel):
    _cmd: str
    id: str
    success: bool
    retdata: Any
    retcode: int
    jid: str
    fun: str
    fun_args: Optional[list] = None
    fun_kwarg: Optional[dict] = None
    user: str
    _stamp: str


class PubData(BaseModel):
    """ Salt LocalClient.run_job response representation """
    jid: int
    minions: list[str]


class CreateJobResponse(BaseModel):
    return_: list[PubData] = Field(alias='return')


class CreateJobRequest(BaseModel):
    tgt: str = '*'
    tgt_type: str = 'glob'
    fun: str = 'test.ping'
    arg: list = []
    kwarg: dict = {}
