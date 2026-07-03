from pydantic import BaseModel, ConfigDict, Field, computed_field

from saltbox_sdk.db.mongo.schemas_base import IDMixin, PyObjectId, QueryParams, SortParams
from saltbox_sdk.db.schemas_base import CreatedModifiedMixin, SkipLimitParams
from saltbox_sdk.event_bus.schemas import (
    ExtraDataCategoryType,
    MinionExtraDataCategoryField,
    MinionExtraDataExtraFieldsPolicy,
)


class ExtraDataCategoryReadOnlyFieldsMixin(BaseModel):
    source: str = Field(title='Source')
    name: str = Field(title='Name')
    type: ExtraDataCategoryType = Field(title='Type')
    extra_fields_policy: MinionExtraDataExtraFieldsPolicy = Field(default=MinionExtraDataExtraFieldsPolicy.IGNORE)


class ExtraDataCategoryEditableFieldsMixin(BaseModel):
    fields: list[MinionExtraDataCategoryField] = Field(default_factory=list)
    minion_fields: list[str] = Field(default_factory=list)

    @computed_field
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


class ExtraDataCategoryListBody(SkipLimitParams, QueryParams, SortParams):
    source: str | None = Field(title='Namespace', default=None)

    model_config = ConfigDict(extra='ignore')


class ExtraDataListBody(SkipLimitParams, SortParams):
    minion_id: PyObjectId = Field(title='Minion Id')
    category_source: str | None = Field(title='Namespace', default=None)
    category_name: str | None = Field(title='Name')
    search: str | None = Field(title='Search', default=None)

    model_config = ConfigDict(extra='ignore')
