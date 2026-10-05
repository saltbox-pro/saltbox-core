from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

from saltbox_sdk.db.mongo.schemas_base import IDMixin, PyObjectId, QueryParams, SortParams
from saltbox_sdk.db.schemas_base import CreatedModifiedMixin, SkipLimitParams
from saltbox_sdk.event_bus.schemas import (
    ExtraDataCategoryType,
    MinionExtraDataCategoryField,
    MinionExtraDataCategoryFieldType,
    MinionExtraDataExtraFieldsPolicy,
)
from saltbox_sdk.exceptions import SaltBoxValidationException


def _clean_field_value(value: Any, field_types: list[MinionExtraDataCategoryFieldType]) -> tuple[bool, Any]:
    for field_type in field_types:
        if field_type == MinionExtraDataCategoryFieldType.DATETIME:
            if isinstance(value, str):
                try:
                    return True, datetime.fromisoformat(value)
                except ValueError:
                    continue
        elif field_type in (MinionExtraDataCategoryFieldType.INT, MinionExtraDataCategoryFieldType.FLOAT):
            if isinstance(value, bool):
                continue
            if field_type == MinionExtraDataCategoryFieldType.FLOAT and isinstance(value, int):
                return True, value

        if isinstance(value, field_type.python_type):
            return True, value

    return False, None


class ExtraDataCategoryReadOnlyFieldsMixin(BaseModel):
    source: str = Field(title='Source')
    name: str = Field(title='Name')
    type: ExtraDataCategoryType = Field(title='Type')
    is_system: bool = Field(default=False, title='Created by system')
    is_manual_data_allowed: bool = Field(default=False, title='Manual data entries allowed')
    is_single_item: bool = Field(default=False)
    fields: list[MinionExtraDataCategoryField] = Field(default_factory=list)
    minion_fields: list[str] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def category_fields(self) -> list[str]:
        return [field.name for field in self.fields if field.name not in self.minion_fields]


class ExtraDataCategoryEditableFieldsMixin(BaseModel):
    title: dict[str, str] | None = Field(default=None)
    description: dict[str, str] | None = Field(default=None)
    icon: str | None = Field(default=None)
    extra_fields_policy: MinionExtraDataExtraFieldsPolicy = Field(default=MinionExtraDataExtraFieldsPolicy.IGNORE)


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
):
    def clean_data(self, data: dict[str, Any]) -> dict[str, Any]:
        fields = {field.name: field for field in self.fields}
        cleaned: dict[str, Any] = {}
        errors: list[str] = []

        for key, value in data.items():
            field = fields.get(key)

            if field is None:
                if self.extra_fields_policy == MinionExtraDataExtraFieldsPolicy.IGNORE:
                    errors.append(f'`{key}`: unknown field')
                else:
                    cleaned[key] = value
                continue

            if not field.types:
                cleaned[key] = value
                continue

            is_valid, cleaned_value = _clean_field_value(value, field.types)
            if is_valid:
                cleaned[key] = cleaned_value
            else:
                errors.append(f'`{key}`: expected {" | ".join(field.types)}')

        if errors:
            msg = f'Invalid extra data: {"; ".join(errors)}'
            raise SaltBoxValidationException(msg)

        return cleaned

    def split_data(self, data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        category_data: dict[str, Any] = {}
        minion_data: dict[str, Any] = {}

        for key, value in data.items():
            if key in self.minion_fields:
                minion_data[key] = value
            elif key in self.category_fields:
                category_data[key] = value
            elif self.extra_fields_policy == MinionExtraDataExtraFieldsPolicy.SAVE_TO_MINION:
                minion_data[key] = value
            elif self.extra_fields_policy == MinionExtraDataExtraFieldsPolicy.SAVE_TO_CATEGORY:
                category_data[key] = value

        return dict(sorted(category_data.items())), minion_data


# REST


def validate_category_field_name(name: str) -> str:
    if '.' in name or name.startswith('$'):
        msg = f'Field name `{name}` must not contain `.` or start with `$`'
        raise SaltBoxValidationException(msg)

    return name


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

    @model_validator(mode='after')
    def validate_fields(self) -> 'ExtraDataCategoryCreateRequestSchema':
        field_names: list[str] = []
        for field in self.fields:
            validate_category_field_name(field.name)
            if field.name in field_names:
                msg = f'Field `{field.name}` is duplicated'
                raise SaltBoxValidationException(msg)
            field_names.append(field.name)

        for minion_field in self.minion_fields:
            if minion_field not in field_names:
                msg = f'Minion field `{minion_field}` is not in category fields'
                raise SaltBoxValidationException(msg)

        return self


class ExtraDataCategoryFieldCreateRequestSchema(MinionExtraDataCategoryField):
    is_minion_field: bool = Field(default=False)

    @field_validator('name')
    @classmethod
    def validate_name(cls, name: str) -> str:
        return validate_category_field_name(name)


class ExtraDataCategoryFieldsOrderRequestSchema(BaseModel):
    field_names: list[str] = Field(min_length=1)

    @field_validator('field_names')
    @classmethod
    def validate_field_names(cls, field_names: list[str]) -> list[str]:
        if len(set(field_names)) != len(field_names):
            msg = 'Field names must be unique'
            raise SaltBoxValidationException(msg)

        return field_names


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
