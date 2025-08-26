import logging
import typing
from functools import cache
from typing import ClassVar, Literal

from pydantic import BaseModel, Field

from saltbox_sdk.db.mongo.schemas_base import IDMixin
from saltbox_sdk.db.schemas_base import CreatedModifiedMixin

logger = logging.getLogger(__name__)

# TODO () : <>
#  - softwares
#  - videos
#  - bios
#  - virtualmachines
#  - users
#  - networks
#  - storages
#  - ports
#  - batteries
#  - cpus
#  - local_users
#  - drives
#  - sounds
#  - hardware
#  - controllers

CategoryType = Literal[
    'inputs',
    'local_groups',
]

CATEGORIES: tuple[CategoryType, ...] = typing.get_args(CategoryType)


class InventoryProtoBase:
    # TODO (a.karmanov): <US373> Looks like related issue https://github.com/python/mypy/issues/11470
    if typing.TYPE_CHECKING:
        @classmethod
        def __hash__(cls) -> int:
            return hash(cls)

    @property
    def category(self) -> CategoryType:
        msg = f'Trying to use an instance of "abstract" {self.__class__.__name__}'
        raise TypeError(msg)


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


def get_proto_for_category(category: CategoryType) -> type[InventoryProtoBase]:
    match category:
        case InventoryInputProto.category: return InventoryInputProto
        case InventoryLocalGroupProto.category: return InventoryLocalGroupProto
        case _: raise TypeError(f'Unsupported category {category}')  # noqa: EM102
