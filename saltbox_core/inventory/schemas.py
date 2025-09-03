import logging
import sys
from functools import cache
from inspect import getmembers, isclass
from typing import TYPE_CHECKING, Any, ClassVar, Literal
from typing import get_args as typing_get_args

from pydantic import BaseModel, ConfigDict, Field, root_validator
from pydantic.fields import FieldInfo

from saltbox_sdk.db.mongo.schemas_base import IDMixin
from saltbox_sdk.db.schemas_base import CreatedModifiedMixin

logger = logging.getLogger(__name__)

CategoryType = Literal[
    'batteries',
    'bios',
    'controllers',
    'cpus',
    # 'drives',
    # 'hardware',
    'inputs',
    'softwares',
    'local_groups',
    # 'local_users',
    # 'networks',
    # 'ports',
    # 'sounds',
    # 'storages',
    # 'users',
    # 'videos',
    # 'virtualmachines',
]

CATEGORIES: tuple[CategoryType, ...] = typing_get_args(CategoryType)


class _InventoryProtoBase:
    """
    For dynamic Inventory models. Not supposed to be used directly.
    """

    category: ClassVar[CategoryType]
    model_fields: ClassVar[dict[str, FieldInfo]]
    _known_fields: ClassVar[set[str] | None] = None

    # TODO (a.karmanov): <US373> Looks like related issue https://github.com/python/mypy/issues/11470
    if TYPE_CHECKING:
        @classmethod
        def __hash__(cls) -> int:
            return hash(cls)

    model_config = ConfigDict(validate_by_name=True, extra='ignore')

    def get_category(self) -> str:
        return self.category

    # @cache seems appropriate, but there is a risk of dangling references for dynamic types
    @classmethod
    def get_known_fields(cls) -> set[str]:
        if cls._known_fields is None:
            known_aliases = {field.alias for field in cls.model_fields.values() if field.alias}
            cls._known_fields = set(cls.model_fields) | known_aliases
        return cls._known_fields

    @root_validator(pre=True)
    def log_extra_fields(cls, values: dict[str, Any]) -> dict[str, Any]:  # noqa: N805
        extra_fields = set(values) - cls.get_known_fields()

        for ext_field in extra_fields:
            logger.warning('Inventory model %s got extra field %s', __name__, ext_field)

        return values


class InventoryMinionSpec(BaseModel):
    master_id: str
    minion_id: str

    def __str__(self) -> str:
        return f'{self.master_id}:{self.minion_id}'


class InventoryCommonMixin:
    category: ClassVar[CategoryType]
    minions: list[InventoryMinionSpec] = Field(description='Relation with minions')


class InventoryModelBase(BaseModel, InventoryCommonMixin, IDMixin, CreatedModifiedMixin): ...
class InventoryCreateSchemaBase(BaseModel, InventoryCommonMixin): ...  # noqa: E302


class InventoryModelFab:
    PROTOTYPE_POSTFIX = 'Proto'

    @classmethod
    def _make_name(cls, proto: type, postfix: str) -> str:
        orig = proto.__name__
        if orig.endswith(cls.PROTOTYPE_POSTFIX):
            orig = orig[:-len(cls.PROTOTYPE_POSTFIX)]
        return orig + postfix

    @staticmethod
    def _make_type(name: str, bases: tuple[type, ...]) -> type:
        new_type = type(name, bases, {})
        assert issubclass(new_type, _InventoryProtoBase)  # noqa
        return new_type

    @classmethod
    @cache
    def get_model(cls, proto: type[_InventoryProtoBase]) -> type[InventoryModelBase]:
        name = cls._make_name(proto, 'Model')
        return cls._make_type(name, (InventoryModelBase, proto))

    @classmethod
    @cache
    def get_create_schema(cls, proto: type[_InventoryProtoBase]) -> type[InventoryCreateSchemaBase]:
        name = cls._make_name(proto, 'CreateSchema')
        return cls._make_type(name, (InventoryCreateSchemaBase, proto))


class InventoryLocalGroupProto(_InventoryProtoBase):
    category: ClassVar[CategoryType] = 'local_groups'
    gid: int
    name: str
    members: list[str]


class InventoryInputProto(_InventoryProtoBase):
    category: ClassVar[CategoryType] = 'inputs'
    caption: str
    type: str
    description: str


class InventorySoftwareProto(_InventoryProtoBase):
    category: ClassVar[CategoryType] = 'softwares'
    arch: str
    comments: str
    filesize: int
    from_: str = Field(alias='from')
    installdate: str
    name: str
    publisher: str
    system_category: str
    version: str


class InventoryBatteryProto(_InventoryProtoBase):
    category: ClassVar[CategoryType] = 'batteries'
    capacity: str
    chemistry: str
    manufacturer: str
    name: str
    real_capacity: str
    serial: str
    voltage: str


class InventoryBiosProto(_InventoryProtoBase):
    category: ClassVar[CategoryType] = 'bios'
    assettag: str
    bdate: str
    bmanufacturer: str
    bversion: str
    mmanufacturer: str
    mmodel: str
    msn: str
    smanufacturer: str
    smodel: str
    ssn: str


class InventoryCpuProto(_InventoryProtoBase):
    category: ClassVar[CategoryType] = 'cpus'
    arch: str
    core: int
    familynumber: int
    manufacturer: str
    model: str
    name: str
    stepping: int
    thread: int


class InventoryControllerProto(_InventoryProtoBase):
    category: ClassVar[CategoryType] = 'controllers'
    manufacturer: str
    name: str
    pcislot: str
    productid: str


def _make_categories_mapping() -> dict[CategoryType, type[_InventoryProtoBase]]:
    mapping: dict[CategoryType, type[_InventoryProtoBase]] = {}
    module = sys.modules[__name__]
    allowed_categories = set(CATEGORIES)

    for name, obj in getmembers(module):
        if isclass(obj) and issubclass(obj, _InventoryProtoBase) and obj is not _InventoryProtoBase:
            logger.debug('Found %s inventory prototype', name)
            if obj.category not in allowed_categories:
                msg = f'Unexpected inventory category {obj.category}'
                raise TypeError(msg)
            mapping[obj.category] = obj

    return mapping


_CATEGORIES_MAPPING = _make_categories_mapping()


def get_proto_for_category(category: CategoryType) -> type[_InventoryProtoBase]:
    proto_type = _CATEGORIES_MAPPING.get(category)
    if not proto_type:
        msg = f'Unsupported category {category}'
        raise TypeError(msg)
    return proto_type
