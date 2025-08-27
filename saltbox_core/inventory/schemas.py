import logging
from functools import cache
from typing import TYPE_CHECKING, ClassVar, Literal
from typing import get_args as typing_get_args

from pydantic import BaseModel, ConfigDict, Field

from saltbox_sdk.db.mongo.schemas_base import IDMixin
from saltbox_sdk.db.schemas_base import CreatedModifiedMixin

logger = logging.getLogger(__name__)

CategoryType = Literal[
    # 'batteries',
    # 'bios',
    # 'controllers',
    # 'cpus',
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


class InventoryProtoBase:
    # TODO (a.karmanov): <US373> Looks like related issue https://github.com/python/mypy/issues/11470
    if TYPE_CHECKING:
        @classmethod
        def __hash__(cls) -> int:
            return hash(cls)

    @property
    def category(self) -> CategoryType:
        msg = f'Trying to use an instance of "abstract" {self.__class__.__name__}'
        raise TypeError(msg)

    model_config = ConfigDict(validate_by_name=True, extra='forbid')

    def get_category(self) -> str:
        return self.category


class InventoryModelBase(BaseModel, IDMixin, CreatedModifiedMixin):
    category: ClassVar[CategoryType]
    minions: list[str] = Field(description='Relation with minions')


class InventoryCreateSchemaBase(BaseModel):
    category: ClassVar[CategoryType]
    minions: list[str] = Field(description='Relation with minions')


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
        assert issubclass(new_type, InventoryProtoBase)  # noqa
        return new_type

    @classmethod
    @cache
    def get_model(cls, proto: type[InventoryProtoBase]) -> type[InventoryModelBase]:
        name = cls._make_name(proto, 'Model')
        return cls._make_type(name, (InventoryModelBase, proto))

    @classmethod
    @cache
    def get_create_schema(cls, proto: type[InventoryProtoBase]) -> type[InventoryCreateSchemaBase]:
        name = cls._make_name(proto, 'CreateSchema')
        return cls._make_type(name, (InventoryCreateSchemaBase, proto))


class InventoryLocalGroupProto(InventoryProtoBase):
    category: ClassVar[CategoryType] = 'local_groups'
    name: str
    member: str


class InventoryInputProto(InventoryProtoBase):
    category: ClassVar[CategoryType] = 'inputs'
    caption: str
    type: str
    description: str


class InventorySoftwareProto(InventoryProtoBase):
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


def get_proto_for_category(category: CategoryType) -> type[InventoryProtoBase]:
    match category:
        case InventoryInputProto.category: return InventoryInputProto
        case InventoryLocalGroupProto.category: return InventoryLocalGroupProto
        case InventorySoftwareProto.category: return InventorySoftwareProto
        case _: raise TypeError(f'Unsupported category {category}')  # noqa: EM102
