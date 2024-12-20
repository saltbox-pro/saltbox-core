from pydantic import BaseModel, Field
from typing import List, Optional, Any


class Jobs(BaseModel):
    jid: str
    tgt: str
    tgt_type: str
    user: str
    fun: str
    arg: List
    kwarg: Optional[dict]
    minions: List[str]
    _stamp: str
    fms_jid_timestamp: str


class JobResponse(BaseModel):
    jid: str
    minions: List[str]


class ModelJobResponse(BaseModel):
    jid: str


class JobReturn(BaseModel):
    id: str
    success: bool
    return_: bool = Field(..., alias='return')
    retcode: int
    jid: str
    fun: str
    fun_args: List
    fun_kwarg: Any
    user: str
    _stamp: str
    cmd: str


class ModelJobReturn(BaseModel):
    result: List[JobReturn]
    cursor: int
    length: int
