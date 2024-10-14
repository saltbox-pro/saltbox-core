from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Optional

from odmantic import EmbeddedModel, Field, Model
from odmantic.config import ODMConfigDict


def datetime_now_sec() -> datetime:
    return datetime.now().astimezone().replace(microsecond=0)


class Grains(EmbeddedModel):
    # zmqversion
    id: str = Field(title='ID')
    host: str = Field(title='Host')
    fqdn: str = Field(title='FQDN')
    master: Optional[str] = Field(title='Master', default=None)
    fqdns: Optional[list] = Field(title='FQDNs', default=None)
    # CPU
    cpu_model: Optional[str] = Field(title='CPU Model', default=None)
    num_cpus: Optional[int] = Field(title='Number of CPUs', default=None)
    cpu_flags: Optional[list] = Field(title='CPU Flags', default=None)
    cpuarch: Optional[str] = Field(title='CPU Architecture', default=None)
    # Memory
    mem_total: Optional[int] = Field(title='Total memory', default=None)
    swap_total: Optional[int] = Field(title='Total swap', default=None)
    # GPU
    gpus: Optional[list] = Field(title='GPUs', default=None)
    num_gpus: Optional[int] = Field(title='Number of GPUs', default=None)
    # OS
    os: Optional[str] = Field(title='OS', default=None)
    osfullname: Optional[str] = Field(title='OS Full Name', default=None)
    osfinger: Optional[str] = Field(title='OS Finger', default=None)
    osrelease: Optional[str] = Field(title='OS Release', default=None)
    osrelease_info: Optional[list] = Field(title='OS Release Info', default=None)
    oscodename: Optional[str] = Field(title='OS Codename', default=None)
    os_family: Optional[str] = Field(title='OS Family', default=None)
    osarch: Optional[str] = Field(title='OS Architecture', default=None)
    disks: Optional[list] = Field(title='Disks', default=None)

    # dns: Optional[dict] = None
    # domain: Optional[str] = None
    # hwaddr_interfaces: Optional[dict] = None
    # ip_gw: Optional[bool] = None
    # ip_interfaces: Optional[dict] = None
    # ip4_gw: Optional[str] = None
    # ip6_gw: Optional[str] = None
    # kernelrelease: Optional[str] = None
    # kernelversion: Optional[str] = None
    # locale_info: Optional[dict] = None
    # localhost: Optional[str] = None
    # path: Optional[str] = None
    # pythonexecutable: Optional[str] = None
    # pythonpath: Optional[list] = None
    # pythonversion: Optional[list] = None
    # saltpath: Optional[str] = None
    # saltversion: Optional[str] = None
    # saltversioninfo: Optional[list] = None
    # server_id: Optional[int] = None
    # systempath: Optional[list] = None
    # uid: Optional[int] = None
    # zmqversion: Optional[str] = None

    model_config: ClassVar[ODMConfigDict] = {'extra': 'allow'}


class Minion(Model):
    minion_id: str = Field(unique=True)
    master: str
    created: datetime = Field(default_factory=datetime_now_sec)
    modified: datetime = Field(default_factory=datetime_now_sec)
    grains: Grains
