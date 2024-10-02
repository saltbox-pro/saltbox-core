from __future__ import annotations

from datetime import datetime

from odmantic import ObjectId
from pydantic import BaseModel, ConfigDict


class GrainsSchema(BaseModel):
    cwd: str | None = None
    host: str | None = None
    ip6_gw: bool | None = None
    cpu_flags: list[str] | None = None
    osfinger: str | None = None
    efi: bool | None = None
    swap_total: int | None = None
    zfs_support: bool | None = None
    disks: list[str] | None = None
    localhost: str | None = None
    ps: str | None = None
    pythonexecutable: str | None = None
    kernel: str | None = None
    kernelrelease: str | None = None
    cpuarch: str | None = None
    gid: int | None = None
    ipv4: list[str] | None = None
    uid: int | None = None
    kernelparams: list | None = None
    osmajorrelease: int | None = None
    groupname: str | None = None
    osfullname: str | None = None
    ip_interfaces: dict[str, list[str]] | None = None
    ssds: list | None = None
    path: str | None = None
    master: str | None = None
    gpus: list | None = None
    osrelease_info: list[int] | None = None
    pythonpath: list[str] | None = None
    oscodename: str | None = None
    hwaddr_interfaces: dict[str, str] | None = None
    saltversioninfo: list[int] | None = None
    shell: str | None = None
    ip6_interfaces: dict[str, list[str]] | None = None
    systempath: list[str] | None = None
    num_gpus: int | None = None
    username: str | None = None
    pythonversion: list[str | int] | None = None
    os_family: str | None = None
    locale_info: dict[str, str] | None = None
    saltversion: str | None = None
    init: str | None = None
    lsb_distrib_codename: str | None = None
    ip4_interfaces: dict[str, list[str]] | None = None
    fqdn_ip4: list[str] | None = None
    domain: str | None = None
    fqdn: str | None = None
    num_cpus: int | None = None
    os: str | None = None
    virtual: str | None = None
    nodename: str | None = None
    efi_secure_boot: bool | None = None
    cpu_model: str | None = None
    mem_total: int | None = None
    lsb_distrib_id: str | None = None
    zfs_feature_flags: bool | None = None
    osarch: str | None = None
    fqdns: list | None = None
    server_id: int | None = None
    zmqversion: str | None = None
    transactional: bool | None = None
    osrelease: str | None = None
    ip4_gw: str | None = None
    lsb_distrib_release: str | None = None
    kernelversion: str | None = None
    pid: int | None = None
    fqdn_ip6: list | None = None
    ip_gw: bool | None = None
    saltpath: str | None = None
    ipv6: list[str] | None = None
    dns: dict | None = None


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
    model_config = ConfigDict(populate_by_name=True)
