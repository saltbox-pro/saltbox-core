from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from saltbox_sdk.db.mongo.schemas_base import IDMixin, PyObjectId
from saltbox_sdk.db.schemas_base import CreatedModifiedMixin
from saltbox_sdk.utilities.helpers import Iso8601ZDatetime


class ExtraDataForMinion(BaseModel):
    minion_id: PyObjectId = Field(title='Minion MongoDB id')
    data: dict = Field(title='Minion data')


class ExtraDataReadOnlyFieldsMixin(BaseModel):
    source: str = Field(title='Source')
    name: str = Field(title='Name')
    data: Any = Field(title='Data')


class ExtraDataEditableFieldsMixin(BaseModel):
    minions: list[ExtraDataForMinion] = Field(title='Minions data', default_factory=list)


class ExtraDataCreateSchema(ExtraDataEditableFieldsMixin, ExtraDataReadOnlyFieldsMixin):
    pass


class ExtraDataUpdateSchema(ExtraDataEditableFieldsMixin):
    model_config = ConfigDict(
        extra='forbid',
    )


class ExtraDataModel(
    IDMixin,
    CreatedModifiedMixin,
    ExtraDataEditableFieldsMixin,
    ExtraDataReadOnlyFieldsMixin,
): ...


# REST


class ExtraDataListItemSchema(BaseModel):
    source: str = Field(title='Source', alias='_source', exclude=True)
    name: str = Field(title='Name', alias='_name', exclude=True)

    model_config = ConfigDict(
        extra='allow',
    )


class CollectionExtraDataListItemSchema(ExtraDataListItemSchema):
    minions_count: int = Field(
        title='Minions count',
        validation_alias='_minions_count',
        serialization_alias='minions_count',
    )


class ExtraDataActions(StrEnum):
    CREATE = 'create'
    READ = 'read'
    UPDATE = 'update'
    DELETE = 'delete'
    LIST = 'list'
    EXPORT = 'export'


class StaticExtraDataItemBaseRequestSchema(BaseModel):
    category_source: str = Field(title='Category source')
    category_name: str = Field(title='Category name')
    data: dict[str, Any] = Field(title='Data')


class StaticExtraDataItemCreateRequestSchema(StaticExtraDataItemBaseRequestSchema):
    minion_ids: list[PyObjectId] = Field(title='Minion IDs', min_length=1)


class StaticExtraDataItemUpdateRequestSchema(StaticExtraDataItemBaseRequestSchema):
    minion_id: PyObjectId = Field(title='Minion ID')


class StaticExtraDataItemSchema(BaseModel):
    id: PyObjectId = Field(alias='_id', title='ID')
    is_system: bool = Field(title='Created by system')
    updated_at: Iso8601ZDatetime = Field(title='Updated at')
    data: dict[str, Any] = Field(title='Data')

    model_config = ConfigDict(populate_by_name=True)


class StaticExtraDataMinionItemSchema(StaticExtraDataItemSchema):
    minion_id: PyObjectId = Field(title='Minion ID')


class StaticExtraDataItemsCreateResponseSchema(BaseModel):
    minions_count: int = Field(title='Minions count')
    items: list[StaticExtraDataMinionItemSchema] = Field(title='Items')
