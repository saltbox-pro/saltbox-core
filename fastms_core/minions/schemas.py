from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field


class GrainsSchema(BaseModel):
    id: str | None = Field(title='ID', default=None)
    host: str | None = Field(title='Host', default=None)
    fqdn: str | None = Field(title='FQDN', default=None)
    master: str | None = Field(title='Master', default=None)
    fqdns: list | None = Field(title='FQDNs', default=None)
    # CPU
    cpu_model: str | None = Field(title='CPU Model', default=None)
    num_cpus: int | None = Field(title='Number of CPUs', default=None)
    cpu_flags: list | None = Field(title='CPU Flags', default=None)
    cpuarch: str | None = Field(title='CPU Architecture', default=None)
    # Memory
    mem_total: int | None = Field(title='Total memory', default=None)
    swap_total: int | None = Field(title='Total swap', default=None)
    # GPU
    gpus: list | None = Field(title='GPUs', default=None)
    num_gpus: int | None = Field(title='Number of GPUs', default=None)
    # OS
    os: str | None = Field(title='OS', default=None)
    osfullname: str | None = Field(title='OS Full Name', default=None)
    osfinger: str | None = Field(title='OS Finger', default=None)
    osrelease: str | None = Field(title='OS Release', default=None)
    osrelease_info: list | None = Field(title='OS Release Info', default=None)
    oscodename: str | None = Field(title='OS Codename', default=None)
    os_family: str | None = Field(title='OS Family', default=None)
    osarch: str | None = Field(title='OS Architecture', default=None)
    disks: list | None = Field(title='Disks', default=None)

    # dns: dict | None = None
    # domain: str | None = None
    # hwaddr_interfaces: dict | None = None
    # ip_gw: bool | None = None
    # ip_interfaces: dict | None = None
    # ip4_gw: str | None = None
    # ip6_gw: str | None = None
    # kernelrelease: str | None = None
    # kernelversion: str | None = None
    # locale_info: dict | None = None
    # localhost: str | None = None
    # path: str | None = None
    # pythonexecutable: str | None = None
    # pythonpath: list | None = None
    # pythonversion: list | None = None
    # saltpath: str | None = None
    # saltversion: str | None = None
    # saltversioninfo: list | None = None
    # server_id: int | None = None
    # systempath: list | None = None
    # uid: int | None = None
    # zmqversion: str | None = None

    model_config = ConfigDict(extra='allow')


class GrainsShortSchema(BaseModel):
    id: str | None = None
    fqdn: str | None = None
    osfullname: str | None = None
    domain: str | None = None
    efi: bool | None = None
    cpu_model: str | None = None
    mem_total: int | None = None

    model_config = ConfigDict(from_attributes=True)


class MinionSchemaBase(BaseModel):
    minion_id: str
    master: str
    created: datetime | None = None
    modified: datetime | None = None


class MinionSchema(MinionSchemaBase):
    grains: GrainsSchema | None = None

    model_config = ConfigDict(extra='allow')


class MinionSchemaCreate(MinionSchemaBase):
    pass


class MinionSchemaUpdate(MinionSchemaBase):
    pass


class MinionListSchema(MinionSchemaBase):
    grains: GrainsShortSchema | None = None

    class Settings:
        projection: ClassVar[dict] = {
            'minion_id': 1,
            'master': 1,
            'grains.id': 1,
            'grains.fqdn': 1,
            'grains.osfullname': 1,
            'grains.domain': 1,
            'grains.efi': 1,
            'grains.cpu_model': 1,
            'grains.mem_total': 1,
            'created': 1,
            'modified': 1,
        }
