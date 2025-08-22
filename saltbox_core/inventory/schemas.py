# from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field
from pydantic._internal._model_construction import ModelMetaclass

from saltbox_sdk.db.mongo.schemas_base import IDMixin
from saltbox_sdk.db.schemas_base import CreatedModifiedMixin


class TypeProperties(ModelMetaclass):
    _CreateSchema = None

    @property
    def CreateSchema(cls) -> type['InventoryCreateSchema']:  # noqa: N802, N805
        if cls._CreateSchema is None:
            cls._CreateSchema = type('CreateSchema', (cls, IDMixin, CreatedModifiedMixin), {})
        return cls._CreateSchema


class InventoryBaseModel(BaseModel, metaclass=TypeProperties):
    # TODO (akraman) FIXME Del
    model_config = ConfigDict(extra='allow')

    minions: list[str] = Field(description='Relation with minions')
    # TODO (akraman) Make ClassVar
    category: str
    #category: ClassVar[str]


class InventoryCreateSchema(InventoryBaseModel, IDMixin, CreatedModifiedMixin): ...


class InventoryLocalGroupModel(InventoryBaseModel):
    #category: ClassVar = 'local_groups'
    category: str = 'local_groups'
    name: str
    member: str


class InventoryInputModel(InventoryBaseModel):
    #category: ClassVar = 'inputs'
    category: str = 'inputs'
    caption: str
    type: str
    description: str


def get_model_for_category(category: str) -> type['InventoryBaseModel']:
    match category:
        case InventoryInputModel.category: return InventoryInputModel
        case InventoryLocalGroupModel.category: return InventoryLocalGroupModel
        case _: raise TypeError(f'Unsupported category {category}')  # noqa: EM102
