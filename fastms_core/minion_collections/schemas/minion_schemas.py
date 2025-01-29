from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field

from fastms_core.db.mongo.schemas_base import PyObjectId
from fastms_core.utilities.helpers import datetime_now_sec


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

    # Disks
    disks: list | None = Field(title='Disks', default=None)

    cwd: str | None = Field(title='CWD', default=None)

    # Networks
    ip_gw: bool | None = Field(title='IP GW', default=None)
    ip4_gw: str | None = Field(title='IPv4 GW', default=None)
    ip6_gw: str | bool | None = Field(title='IPv6 GW', default=None)
    dns: dict[str, Any] | None = Field(title='DNS', default=None)
    server_id: int | None = Field(title='Server ID', default=None)
    localhost: str | None = Field(title='Localhost', default=None)
    domain: str | None = Field(title='Domain', default=None)
    hwaddr_interfaces: dict[str, str] | None = Field(title='HW interfaces', default=None)
    ip4_interfaces: dict[str, list[str]] | None = Field(title='IPv4 interfaces list', default=None)
    ip6_interfaces: dict[str, list[str]] | None = Field(title='IPv6 interfaces list', default=None)
    ipv4: list[str] | None = Field(title='IPv4 list', default=None)
    ipv6: list[str] | None = Field(title='IPv6 list', default=None)
    fqdn_ip4: list[str] | None = Field(title='FQDN IPv4 list', default=None)
    fqdn_ip6: list[str] | None = Field(title='FQDN IPv6 list', default=None)
    ip_interfaces: dict[str, list[str]] | None = Field(title='IP interfaces list', default=None)

    # Kernel
    kernelparams: list[list[Any]] | None = Field(title='Kernel params', default=None)
    locale_info: dict[str, str] | None = Field(title='Local info', default=None)
    kernel: str | None = Field(title='Kernel', default=None)
    nodename: str | None = Field(title='Node name', default=None)
    kernelrelease: str | None = Field(title='Kernel release', default=None)
    kernelversion: str | None = Field(title='Kernel version', default=None)
    init: str | None = Field(title='Init', default=None)
    lsb_distrib_id: str | None = Field(title='LSB distrib ID', default=None)
    lsb_distrib_release: str | None = Field(title='LSB distrib release', default=None)
    lsb_distrib_codename: str | None = Field(title='LSB distrib codename', default=None)

    # Baseboard
    biosversion: str | None = Field(title='BIOS version', default=None)
    biosvendor: str | None = Field(title='BIOS vendor', default=None)
    boardname: str | None = Field(title='Board name', default=None)
    productname: str | None = Field(title='Product name', default=None)
    manufacturer: str | None = Field(title='Manufacturer', default=None)
    biosreleasedate: str | None = Field(title='BIOS release date', default=None)
    uuid: str | None = Field(title='UUID', default=None)
    serialnumber: str | None = Field(title='Serial number', default=None)

    virtual: str | None = Field(title='Virtual', default=None)
    ps: str | None = Field(title='ps', default=None)
    osmajorrelease: int | None = Field(title='OS major release', default=None)
    path: str | None = Field(title='Path', default=None)
    systempath: list[str] | None = Field(title='System paths list', default=None)
    pythonexecutable: str | None = Field(title='Python executable', default=None)
    pythonpath: list[str] | None = Field(title='Python paths list', default=None)
    pythonversion: list[Any] | None = Field(title='Python version', default=None)
    pythonversionstring: str | None = Field(title='Python version string', default=None)
    saltpath: str | None = Field(title='Salt path', default=None)
    saltversion: str | None = Field(title='Salt version', default=None)
    saltversioninfo: list[int] | None = Field(title='Salt version info', default=None)
    zmqversion: str | None = Field(title='ZMQ version', default=None)
    ssds: list[str] | None = Field(title='SSDs', default=None)
    shell: str | None = Field(title='Shell', default=None)
    transactional: bool | None = Field(title='Transactional', default=None)
    efi: bool | None = Field(title='EFI', default=None)
    efi_secure_boot: bool | None = Field(
        title='EFI secure boot', default=None, alias='efi-secure-boot', serialization_alias='efi-secure-boot'
    )
    username: str | None = Field(title='Username', default=None)
    groupname: str | None = Field(title='Groupname', default=None)
    pid: int | None = Field(title='PID', default=None)
    gid: int | None = Field(title='GID', default=None)
    uid: int | None = Field(title='UID', default=None)
    zfs_support: bool | None = Field(title='ZFS support', default=None)
    zfs_feature_flags: bool | None = Field(title='ZFS feature flags', default=None)

    model_config = ConfigDict(
        extra='allow',
        json_schema_extra={'additionalProperties': {'type': 'object'}},
    )


class GrainsShortSchema(BaseModel):
    id: str | None = None
    fqdn: str | None = None
    osfullname: str | None = None
    domain: str | None = None
    efi: bool | None = None
    cpu_model: str | None = None
    mem_total: int | None = None


class MinionBaseSchema(BaseModel):
    id: PyObjectId | None = Field(alias='_id', default=None)
    minion_id: str = Field(title='Minion ID')
    master: str = Field(title='Master')
    created: datetime = Field(default_factory=datetime_now_sec)
    modified: datetime = Field(default_factory=datetime_now_sec)


class MinionSchema(MinionBaseSchema):
    grains: GrainsSchema | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def additional_grains(self) -> dict[str, Any]:
        additional_grains = {}
        if self.grains:
            for key, val in self.grains.model_dump().items():
                if key not in GrainsSchema.model_fields.keys():
                    additional_grains[key] = val

        return additional_grains


class MinionCreateSchema(MinionSchema):
    pass


class MinionUpdateSchema(MinionSchema):
    pass


class MinionListSchema(MinionBaseSchema):
    grains: GrainsShortSchema | None = None
