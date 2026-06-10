from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from saltbox_sdk.db.mongo.schemas_base import IDMixin, PyObjectId, QueryParams, SortParams
from saltbox_sdk.db.schemas_base import CreatedModifiedMixin, SkipLimitParams


class ExtraDataCategoryFieldType(StrEnum):
    INT = 'int'
    FLOAT = 'float'
    BOOL = 'bool'
    STR = 'str'
    LIST = 'list'
    DICT = 'dict'
    DATETIME = 'datetime'
    OTHER = 'other'


class ExtraDataCategoryField(BaseModel):
    type: ExtraDataCategoryFieldType = Field(title='Type', default=ExtraDataCategoryFieldType.OTHER)
    can_be_none: bool = Field(title='Can be None', default=False)
    default: Any = Field(title='Default Value', default=None)


class ExtraDataCategoryReadOnlyFieldsMixin(BaseModel):
    # source: str = Field(title='Source') -> collector.namespace
    collector_id: PyObjectId = Field(title='Collector ID')
    name: str = Field(title='Name', examples=['software', 'cpu'])


class ExtraDataCategoryEditableFieldsMixin(BaseModel):
    fields: dict[str, ExtraDataCategoryField] = Field(title='Fields', default={})

    category_fields: list[str] = Field(title='Category Fields', default_factory=list)
    minion_fields: list[str] = Field(title='Minion Fields', default_factory=list)


class ExtraDataCategoryAggregatedFieldsMixin(BaseModel):
    namespace: str = Field(title='Collector namespace')
    is_preinstalled: bool = Field(title='Is preinstalled')


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
    ExtraDataCategoryAggregatedFieldsMixin,
): ...


# REST


class ExtraDataCategoryListBody(SkipLimitParams, QueryParams, SortParams):
    model_config = ConfigDict(extra='ignore')


class ExtraDataCategoryCreateRequestSchema(
    ExtraDataCategoryEditableFieldsMixin, ExtraDataCategoryReadOnlyFieldsMixin
): ...


# OPA


class ExtraDataCategoryActions(StrEnum):
    CREATE = 'create'
    READ = 'read'
    LIST = 'list'
    RUN = 'run'
