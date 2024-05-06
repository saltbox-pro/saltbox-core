from typing import Union, Any

from pydantic import BaseModel


class Job(BaseModel):
    # example:
    # {
    #     "jid": "20240422071217916112",
    #     "tgt_type": "glob",
    #     "tgt": "*",
    #     "user": "root",
    #     "fun": "test.ping",
    #     "arg": [],
    #     "minions": ["master.master"],
    #     "missing": [],
    #     "_stamp": "2024-04-22T07:12:17.932302"
    # }
    jid: str
    tgt: str
    tgt_type: str
    user: str
    fun: str
    arg: Union[None, list] = None
    kwarg: Union[None, dict] = None
    minions: list[str]
    _stamp: str


class JobPost(BaseModel):
    tgt: str = '*'
    tgt_type: str = "glob"
    fun: str = 'test.ping'
    arg: Union[None, list] = None
    kwarg: Union[None, dict] = None


class JobResult(BaseModel):
    # example:
    # {
    #     "cmd": "_return",
    #     "id": "master.master",
    #     "success": True,
    #     "return": True,
    #     "retcode": 0,
    #     "jid": "20240422081827358198",
    #     "fun": "test.ping",
    #     "fun_args": [],
    #     "user": "root",
    #     "_stamp": "2024-04-22T08:18:27.509512"
    # }
    _cmd: str
    id: str
    success: bool
    retdata: Any
    retcode: int
    jid: str
    fun: str
    fun_args: Union[None, list] = None
    fun_kwarg: Union[None, dict] = None
    user: str
    _stamp: str
