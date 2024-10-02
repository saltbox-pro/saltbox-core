from __future__ import annotations

from datetime import datetime
from typing import Optional

from odmantic import EmbeddedModel, Field, Model


def datetime_now_sec() -> datetime:
    return datetime.now().astimezone().replace(microsecond=0)


class Grains(EmbeddedModel):
    cwd: Optional[str] = Field(title='Current working directory', default=None)
    host: Optional[str] = None
    ip6_gw: Optional[bool] = None
    cpu_flags: Optional[list] = None  # Field(default_factory=list)
    osfinger: Optional[str] = None
    efi: Optional[bool] = None
    swap_total: Optional[int] = None
    zfs_support: Optional[bool] = None
    disks: Optional[list] = None
    localhost: Optional[str] = None
    ps: Optional[str] = None
    pythonexecutable: Optional[str] = None
    kernel: Optional[str] = None
    kernelrelease: Optional[str] = None
    cpuarch: Optional[str] = None
    gid: Optional[int] = None
    ipv4: Optional[list] = None
    uid: Optional[int] = None
    kernelparams: Optional[list] = None
    osmajorrelease: Optional[int] = None
    groupname: Optional[str] = None
    osfullname: Optional[str] = None
    ip_interfaces: Optional[dict] = None
    ssds: Optional[list] = None
    path: Optional[str] = None
    master: Optional[str] = None
    gpus: Optional[list] = None
    osrelease_info: Optional[list] = None
    pythonpath: Optional[list] = None
    oscodename: Optional[str] = None
    hwaddr_interfaces: Optional[dict] = None
    saltversioninfo: Optional[list] = None
    shell: Optional[str] = None
    ip6_interfaces: Optional[dict] = None
    systempath: Optional[list] = None
    num_gpus: Optional[int] = None
    username: Optional[str] = None
    pythonversion: Optional[list] = None
    os_family: Optional[str] = None
    locale_info: Optional[dict] = None
    saltversion: Optional[str] = None
    init: Optional[str] = None
    lsb_distrib_codename: Optional[str] = None
    ip4_interfaces: Optional[dict] = None
    fqdn_ip4: Optional[list] = None
    domain: Optional[str] = None
    fqdn: Optional[str] = None
    num_cpus: Optional[int] = None
    os: Optional[str] = None
    virtual: Optional[str] = None
    nodename: Optional[str] = None
    efi_secure_boot: Optional[bool] = None
    cpu_model: Optional[str] = None
    mem_total: Optional[int] = None
    lsb_distrib_id: Optional[str] = None
    zfs_feature_flags: Optional[bool] = None
    osarch: Optional[str] = None
    fqdns: Optional[list] = None
    server_id: Optional[int] = None
    zmqversion: Optional[str] = None
    transactional: Optional[bool] = None
    osrelease: Optional[str] = None
    ip4_gw: Optional[str] = None
    lsb_distrib_release: Optional[str] = None
    kernelversion: Optional[str] = None
    pid: Optional[int] = None
    fqdn_ip6: Optional[list] = None
    ip_gw: Optional[bool] = None
    saltpath: Optional[str] = None
    ipv6: Optional[list] = None
    dns: Optional[dict] = None


class Minion(Model):
    minion_id: str
    master: str
    created: datetime = Field(default_factory=datetime_now_sec)
    modified: datetime = Field(default_factory=datetime_now_sec)
    grains: Grains
