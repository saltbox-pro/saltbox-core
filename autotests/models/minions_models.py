from __future__ import annotations

from typing import List, Optional, Union, Dict

from pydantic import BaseModel, Field


class Gpu(BaseModel):
    vendor: str
    model: str


class Dns(BaseModel):
    nameservers: List[str]
    ip4_nameservers: List[str]
    ip6_nameservers: List
    sortlist: List
    domain: str
    search: List[str]
    options: List


class HwaddrInterfaces(BaseModel):
    lo: str
    eth0: str


class Ip4Interfaces(BaseModel):
    lo: List[str]
    eth0: List[str]


class Ip6Interfaces(BaseModel):
    lo: List
    eth0: List


class IpInterfaces(BaseModel):
    lo: List[str]
    eth0: List[str]


class LocaleInfo(BaseModel):
    defaultlanguage: str
    defaultencoding: str
    detectedencoding: str
    timezone: str


class Systemd(BaseModel):
    version: str
    features: str


class Nic4Interface(BaseModel):
    iface_name: str
    ip: str
    mac: str


class Grains(BaseModel):
    id: str
    host: str
    fqdn: str
    master: str
    fqdns: List
    cpu_model: str
    num_cpus: int
    cpu_flags: List[str]
    cpuarch: str
    mem_total: int
    swap_total: int
    gpus: List[Gpu]
    num_gpus: int
    os: str
    osfullname: str
    osfinger: str
    osrelease: str
    osrelease_info: List[Union[int, str]]
    oscodename: str
    os_family: str
    osarch: str
    disks: List[str]
    cwd: str
    ip_gw: bool
    ip4_gw: str
    ip6_gw: bool
    dns: Dns
    machine_id: str
    server_id: int
    localhost: str
    domain: str
    hwaddr_interfaces: HwaddrInterfaces
    ip4_interfaces: Ip4Interfaces
    ip6_interfaces: Ip6Interfaces
    ipv4: List[str]
    ipv6: List
    fqdn_ip4: List[str]
    fqdn_ip6: List
    ip_interfaces: IpInterfaces
    kernelparams: List[List[Optional[str]]]
    locale_info: LocaleInfo
    kernel: str
    nodename: str
    kernelrelease: str
    kernelversion: str
    systemd: Systemd
    init: str
    lsb_distrib_id: str
    lsb_distrib_description: str
    lsb_distrib_release: str
    lsb_distrib_codename: str
    biosversion: str
    productname: str
    manufacturer: str
    biosreleasedate: str
    uuid: str
    serialnumber: str
    virtual: str
    ps: str
    osmajorrelease: int
    path: str
    systempath: List[str]
    pythonexecutable: str
    pythonpath: List[str]
    pythonversion: List[Union[int, str]]
    saltpath: str
    saltversion: str
    saltversioninfo: List[int]
    zmqversion: str
    nic4_interfaces: List[Nic4Interface]
    pythonversionstring: str
    ssds: List
    minion_type: str
    shell: str
    transactional: bool
    efi: bool
    efi_secure_boot: bool = Field(..., alias='efi-secure-boot')
    mdadm: List
    username: str
    groupname: str
    pid: int
    gid: int
    uid: int
    zfs_support: bool
    zfs_feature_flags: bool


class MinionModel(BaseModel):
    minion_id: str
    master: str
    created: str
    modified: str
    grains: Grains
    _id: str


class GrainsToMinionList(BaseModel):
    id: str
    fqdn: str
    osfullname: str
    domain: str
    efi: bool
    cpu_model: str
    mem_total: int


class Datum(BaseModel):
    minion_id: str
    master: str
    created: str
    modified: str
    _id: str
    grains: GrainsToMinionList


class MinionsListModel(BaseModel):
    total: int
    data: List[Datum]


class ModelItem(BaseModel):
    name: str
    label: str


class CollectionsListModel(BaseModel):
    total: int
    data: List


class CreateCollectionModel(BaseModel):
    query: Dict
    title: str
    id: str
