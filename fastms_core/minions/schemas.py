from datetime import datetime
from typing import ClassVar

from beanie import PydanticObjectId
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field, field_validator

from fastms_core.db.mongo.schemas_base import MongoQueryBaseSchema, PaginatedListQueryParams


def datetime_now_sec() -> datetime:
    return datetime.now().astimezone().replace(microsecond=0)


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


class MinionSchemaBase(BaseModel):
    minion_id: str = Field(title='Minion ID')
    master: str = Field(title='Master')
    created: datetime = Field(default_factory=datetime_now_sec)
    modified: datetime = Field(default_factory=datetime_now_sec)


class MinionSchema(MinionSchemaBase):
    grains: GrainsSchema | None = None


class MinionSchemaCreate(MinionSchema):
    pass


class MinionSchemaUpdate(MinionSchema):
    pass


class MinionListSchema(MinionSchemaBase):
    id: PydanticObjectId = Field(alias='_id', serialization_alias='_id')
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


class MinionsListQueryParams(PaginatedListQueryParams, MongoQueryBaseSchema):
    collection_id: PydanticObjectId | None = None

    model_config: ClassVar[ConfigDict] = {'extra': 'forbid'}


class MinionFilterValuesQueryParams(MongoQueryBaseSchema):
    model_configg: ClassVar[ConfigDict] = {'extra': 'forbid'}
    field: str = Field(
        description='Field name to get unique values',
        examples=['grains.os', 'grains.cpu_model', 'grains.mem_total'],
        json_schema_extra={'example': 'grains.os'},
    )

    @field_validator('field')
    @classmethod
    def validate_field(cls, value: str) -> str:
        if '.' not in value and value not in MinionSchema.model_fields:
            raise RequestValidationError(
                errors=[
                    {
                        'loc': ['query', 'field'],
                        'msg': f'Invalid field: {value}',
                        'type': 'value_error',
                        'input': value,
                    }
                ]
            )

        if '.' in value:
            field_name_chain = value.split('.')

            if field_name_chain[0] == 'grains' and field_name_chain[1] not in GrainsSchema.model_fields:
                raise RequestValidationError(
                    errors=[
                        {
                            'loc': ['field', 'field'],
                            'msg': f'Invalid field: {value}',
                            'type': 'value_error',
                            'input': value,
                        }
                    ]
                )
        return value


class MinionCollectionBaseSchema(MongoQueryBaseSchema):
    title: str = Field(title='Title')


class MinionCollectionDBSchema(MinionCollectionBaseSchema):
    id: PydanticObjectId = Field(title='ID', alias='_id', serialization_alias='id')


class MinionCollectionSchema(MinionCollectionDBSchema):
    pass


class MinionCollectionCreateSchema(MinionCollectionBaseSchema):
    pass


class MinionCollectionUpdateSchema(MinionCollectionBaseSchema):
    pass


class MinionCollectionListSchema(MinionCollectionDBSchema):
    pass


class MinionCollectionListQueryParams(PaginatedListQueryParams):
    model_config: ClassVar[ConfigDict] = {'extra': 'forbid'}
