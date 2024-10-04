from __future__ import annotations

from datetime import datetime

from odmantic import ObjectId
from pydantic import BaseModel, ConfigDict


class GrainsSchema(BaseModel):
    id: str
    host: str
    fqdn: str
    master: str | None = None
    fqdns: list | None = None
    # CPU
    cpu_model: str | None = None
    num_cpus: int | None = None
    cpu_flags: list | None = None
    cpuarch: str | None = None
    # Memory
    mem_total: int | None = None
    swap_total: int | None = None
    # GPU
    gpus: list | None = None
    num_gpus: int | None = None
    # OS
    os: str | None = None
    osfullname: str | None = None
    osfinger: str | None = None
    osrelease: str | None = None
    osrelease_info: list | None = None
    oscodename: str | None = None
    os_family: str | None = None
    osarch: str | None = None
    disks: list | None = None

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


class MinionSchemaBase(BaseModel):
    minion_id: str
    master: str
    grains: GrainsSchema | None = None


class MinionSchemaInDBBase(MinionSchemaBase):
    id: ObjectId | None = None
    created: datetime | None = None
    modified: datetime | None = None
    model_config = ConfigDict(from_attributes=True)


class MinionSchemaCreate(MinionSchemaBase):
    pass


class MinionSchemaUpdate(MinionSchemaBase):
    pass


class MinionSchema(MinionSchemaInDBBase):
    model_config = ConfigDict(populate_by_name=True, extra='allow')
