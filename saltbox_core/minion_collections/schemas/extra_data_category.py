from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from saltbox_sdk.db.mongo.schemas_base import IDMixin, PyObjectId, QueryParams, SortParams
from saltbox_sdk.db.schemas_base import CreatedModifiedMixin, SkipLimitParams
from saltbox_sdk.event_bus.schemas import (
    ExtraDataCategoryType,
    MinionExtraDataCategoryField,
    MinionExtraDataExtraFieldsPolicy,
)
from saltbox_sdk.exceptions import SaltBoxValidationException


class ExtraDataCategoryReadOnlyFieldsMixin(BaseModel):
    source: str = Field(title='Source')
    name: str = Field(title='Name')
    type: ExtraDataCategoryType = Field(title='Type')
    is_system: bool = Field(default=False, title='Created by system')
    is_manual_data_allowed: bool = Field(default=False, title='Manual data entries allowed')
    is_single_item: bool = Field(default=False)


class ExtraDataCategoryEditableFieldsMixin(BaseModel):
    title: dict[str, str] | None = Field(default=None)
    description: dict[str, str] | None = Field(default=None)
    icon: str | None = Field(default=None)
    extra_fields_policy: MinionExtraDataExtraFieldsPolicy = Field(default=MinionExtraDataExtraFieldsPolicy.IGNORE)
    fields: list[MinionExtraDataCategoryField] = Field(default_factory=list)
    minion_fields: list[str] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def category_fields(self) -> list[str]:
        return [field.name for field in self.fields if field.name not in self.minion_fields]


class ExtraDataCategoryCreateSchema(ExtraDataCategoryEditableFieldsMixin, ExtraDataCategoryReadOnlyFieldsMixin):
    pass


class ExtraDataCategoryUpdateSchema(ExtraDataCategoryEditableFieldsMixin):
    model_config = ConfigDict(
        extra='forbid',
    )


class ExtraDataCategoryModel(
    IDMixin,
    CreatedModifiedMixin,
    ExtraDataCategoryEditableFieldsMixin,
    ExtraDataCategoryReadOnlyFieldsMixin,
): ...


# REST


class ExtraDataCategoryActions(StrEnum):
    CREATE = 'create'
    READ = 'read'
    UPDATE = 'update'
    DELETE = 'delete'
    LIST = 'list'


class ExtraDataCategoryCreateRequestSchema(BaseModel):
    name: str = Field(title='Name')
    type: ExtraDataCategoryType = Field(title='Type')
    extra_fields_policy: MinionExtraDataExtraFieldsPolicy = Field(default=MinionExtraDataExtraFieldsPolicy.IGNORE)
    fields: list[MinionExtraDataCategoryField] = Field(default_factory=list)
    minion_fields: list[str] = Field(default_factory=list)
    title: dict[str, str] | None = Field(default=None)
    description: dict[str, str] | None = Field(default=None)
    icon: str | None = Field(default=None)
    is_single_item: bool = Field(default=False)


class ExtraDataCategoryListBody(SkipLimitParams, QueryParams, SortParams):
    source: str | None = Field(title='Namespace', default=None)

    model_config = ConfigDict(extra='ignore')


class ExtraDataQueryBaseBody(SortParams):
    category_id: PyObjectId | None = Field(title='Category ID', default=None)
    category_source: str | None = Field(title='Namespace', default=None)
    category_name: str | None = Field(title='Name', default=None)
    search: str | None = Field(title='Search', default=None)

    model_config = ConfigDict(extra='ignore')

    @model_validator(mode='after')
    def validate_category(self) -> 'ExtraDataQueryBaseBody':
        if self.category_id is not None:
            if self.category_source is not None or self.category_name is not None:
                msg = 'Only one of `category_id` or `category_source` + `category_name` can be set'
                raise SaltBoxValidationException(msg)
        elif self.category_source is None or self.category_name is None:
            msg = 'One of `category_id` or both `category_source` and `category_name` must be set'
            raise SaltBoxValidationException(msg)

        return self


class MinionExtraDataQueryBody(ExtraDataQueryBaseBody):
    minion_id: PyObjectId = Field(title='Minion Id')
    collection_slug: str | None = Field(title='Collection slug', default=None)


class CollectionExtraDataQueryBody(ExtraDataQueryBaseBody):
    collection_id: PyObjectId | None = Field(title='Collection ID', default=None)
    collection_slug: str | None = Field(title='Collection slug', default=None)

    @model_validator(mode='after')
    def validate_collection(self) -> 'CollectionExtraDataQueryBody':
        if self.collection_id is None and self.collection_slug is None:
            msg = 'One of `collection_id` or `collection_slug` must be set'
            raise SaltBoxValidationException(msg)

        if self.collection_id is not None and self.collection_slug is not None:
            msg = 'Only one of `collection_id` or `collection_slug` can be set'
            raise SaltBoxValidationException(msg)

        return self


class ExtraDataListBody(SkipLimitParams, MinionExtraDataQueryBody): ...


class CollectionExtraDataListBody(SkipLimitParams, CollectionExtraDataQueryBody): ...
