import typing
from functools import cache
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from saltbox_sdk.db.mongo.schemas_base import IDMixin
from saltbox_sdk.db.schemas_base import CreatedModifiedMixin

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


class InventoryProtoBase(BaseModel):
    # TODO (a.karmanov): <US327> FIXME Del
    model_config = ConfigDict(extra='allow')

    minions: list[str] = Field(description='Relation with minions')
    category: ClassVar[CategoryType]

    _is_proto: ClassVar[bool] = True

    @model_validator(mode='before')
    @classmethod
    def check_is_not_prototype(cls, data: Any) -> Any:
        if cls._is_proto:
            msg = 'Trying to init prototype of inventory model'
            raise TypeError(msg)
        return data


class InventoryModelBase(InventoryProtoBase, IDMixin, CreatedModifiedMixin):
    _is_proto = False


class InventoryCreateSchemaBase(InventoryProtoBase):
    _is_proto = False


class InventoryModelFab:
    @staticmethod
    def _make_type(name: str, bases: tuple[type, ...]) -> type:
        new_type = type(name, bases, {})
        assert issubclass(new_type, InventoryProtoBase)  # noqa: S101
        new_type._is_proto = False
        return new_type

    @classmethod
    @cache
    def get_model(cls, proto: type[InventoryProtoBase]) -> type[InventoryModelBase]:
        return cls._make_type('Model', (proto, IDMixin, CreatedModifiedMixin))

    @classmethod
    @cache
    def get_create_schema(cls, proto: type[InventoryProtoBase]) -> type[InventoryCreateSchemaBase]:
        return cls._make_type('CreateSchema', (proto,))


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
