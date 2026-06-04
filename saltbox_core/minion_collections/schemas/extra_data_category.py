from pydantic import BaseModel, ConfigDict, Field

from saltbox_sdk.db.mongo.schemas_base import IDMixin
from saltbox_sdk.db.schemas_base import CreatedModifiedMixin


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
