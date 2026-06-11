from pydantic import BaseModel, ConfigDict, Field

from saltbox_sdk.db.mongo.schemas_base import IDMixin, PyObjectId, QueryParams, SortParams
from saltbox_sdk.db.schemas_base import CreatedModifiedMixin, SkipLimitParams


class ExtraDataCategoryReadOnlyFieldsMixin(BaseModel):
    source: str = Field(title='Source')
    name: str = Field(title='Name')


class ExtraDataCategoryEditableFieldsMixin(BaseModel):
    category_fields: list[str] = Field(title='Category Fields', default_factory=list)
    minion_fields: list[str] = Field(title='Minion Fields', default_factory=list)


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
