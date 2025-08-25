from functools import cache
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from saltbox_sdk.db.mongo.schemas_base import IDMixin
from saltbox_sdk.db.schemas_base import CreatedModifiedMixin


class InventoryBaseProto(BaseModel):
    # TODO (akraman) FIXME Del
    model_config = ConfigDict(extra='allow')

    minions: list[str] = Field(description='Relation with minions')
    # TODO (akraman) Make ClassVar
    category: str
    # category: ClassVar[str]

    _is_proto: ClassVar[bool] = True

    @model_validator(mode='before')
    @classmethod
    def check_is_not_prototype(cls, data: Any) -> Any:
        if cls._is_proto:
            msg = 'Trying to init prototype of inventory model'
            raise TypeError(msg)
        return data


class InventoryBaseModel(InventoryBaseProto, IDMixin, CreatedModifiedMixin):
    _is_proto = False
class InventoryBaseCreateSchema(InventoryBaseProto):
    _is_proto = False


class InventoryTypeFab:
    @staticmethod
    def _make_type(name: str, bases: tuple[type, ...]) -> type:
        new_type = type(name, bases, {})
        assert issubclass(new_type, InventoryBaseProto)  # noqa: S101
        new_type._is_proto = False
        return new_type

    @classmethod
    @cache
    def get_model(cls, proto: type[InventoryBaseProto]) -> type[InventoryBaseModel]:
        return cls._make_type('Model', (proto, IDMixin, CreatedModifiedMixin))

    @classmethod
    @cache
    def get_create_schema(cls, proto: type[InventoryBaseProto]) -> type[InventoryBaseCreateSchema]:
        return cls._make_type('CreateSchema', (proto,))


class InventoryLocalGroupProto(InventoryBaseProto):
    # category: ClassVar = 'local_groups'
    name: str
    member: str


class InventoryInputProto(InventoryBaseProto):
    # category: ClassVar = 'inputs'
    caption: str
    type: str
    description: str


def get_proto_for_category(category: str) -> type[InventoryBaseProto]:
    match category:
        case 'inputs': return InventoryInputProto
        case 'local_groups': return InventoryLocalGroupProto
        case _: raise TypeError(f'Unsupported category {category}')  # noqa: EM102
