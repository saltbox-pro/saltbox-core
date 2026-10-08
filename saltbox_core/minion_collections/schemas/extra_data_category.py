from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from saltbox_sdk.db.mongo.schemas_base import IDMixin, PyObjectId, QueryParams, SortParams
from saltbox_sdk.db.schemas_base import CreatedModifiedMixin, SkipLimitParams
from saltbox_sdk.event_bus.schemas import (
    ExtraDataCategoryType,
    MinionExtraDataCategoryField,
    MinionExtraDataCategoryFieldType,
    MinionExtraDataExtraFieldsPolicy,
)
from saltbox_sdk.exceptions import SaltBoxValidationException


def _clean_field_value(value: Any, field_type: MinionExtraDataCategoryFieldType) -> tuple[bool, Any]:
    if field_type == MinionExtraDataCategoryFieldType.DATETIME and isinstance(value, str):
        try:
            return True, datetime.fromisoformat(value)
        except ValueError:
            return False, None

    if field_type in (MinionExtraDataCategoryFieldType.INT, MinionExtraDataCategoryFieldType.FLOAT):
        if isinstance(value, bool):
            return False, None
        if field_type == MinionExtraDataCategoryFieldType.FLOAT and isinstance(value, int):
            return True, value

    if isinstance(value, field_type.python_type):
        return True, value

    return False, None


def _cast_filter_value(value: Any, field_type: MinionExtraDataCategoryFieldType) -> Any:
    is_valid, cleaned_value = _clean_field_value(value, field_type)
    if is_valid:
        return cleaned_value

    if isinstance(value, str) and field_type in (
        MinionExtraDataCategoryFieldType.INT,
        MinionExtraDataCategoryFieldType.FLOAT,
    ):
        try:
            return field_type.python_type(value)
        except ValueError:
            return value

    if (
        field_type == MinionExtraDataCategoryFieldType.STR
        and isinstance(value, int | float)
        and not isinstance(value, bool)
    ):
        return str(value)

    return value


class ExtraDataCategoryReadOnlyFieldsMixin(BaseModel):
    source: str = Field(title='Source')
    name: str = Field(title='Name')
    type: ExtraDataCategoryType = Field(title='Type')
    is_system: bool = Field(default=False, title='Created by system')
    is_manual_data_allowed: bool = Field(default=False, title='Manual data entries allowed')
    is_single_item: bool = Field(default=False)
    fields: list[MinionExtraDataCategoryField] = Field(default_factory=list)


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
    @property
    def category_fields(self) -> list[str]:
        return [field.name for field in self.fields if not field.is_minion_field]

    @property
    def minion_fields(self) -> list[str]:
        return [field.name for field in self.fields if field.is_minion_field]

    def cast_filter_value(self, field_name: str, value: Any) -> Any:
        field = next((field for field in self.fields if field.name == field_name), None)

        if field is None:
            return value

        if not isinstance(value, dict):
            return _cast_filter_value(value, field.type)

        cast_value: dict[str, Any] = {}

        for lookup, lookup_value in value.items():
            if lookup in ('$eq', '$ne', '$gt', '$gte', '$lt', '$lte'):
                cast_value[lookup] = _cast_filter_value(lookup_value, field.type)
            elif lookup in ('$in', '$nin') and isinstance(lookup_value, list):
                cast_value[lookup] = [_cast_filter_value(item, field.type) for item in lookup_value]
            else:
                cast_value[lookup] = lookup_value

        return cast_value

    def clean_data(self, data: dict[str, Any], *, is_minion_data_only: bool = False) -> dict[str, Any]:
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

            if value is None or value == '':
                if field.is_empty_allowed:
                    cleaned[key] = value
                else:
                    errors.append(f'`{key}`: must not be empty')
                continue

            is_valid, cleaned_value = _clean_field_value(value, field.type)
            if is_valid:
                cleaned[key] = cleaned_value
            else:
                errors.append(f'`{key}`: expected {field.type}')

        for field in self.fields:
            is_required = not field.is_empty_allowed and (field.is_minion_field or not is_minion_data_only)
            if is_required and field.name not in data:
                errors.append(f'`{field.name}`: must not be empty')

        if errors:
            msg = f'Invalid extra data: {"; ".join(errors)}'
            raise SaltBoxValidationException(msg)

        return cleaned

    def split_data(self, data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        fields = {field.name: field for field in self.fields}
        category_data: dict[str, Any] = {}
        minion_data: dict[str, Any] = {}

        for key, value in data.items():
            field = fields.get(key)

            if field is not None:
                if field.is_minion_field:
                    minion_data[key] = value
                else:
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

        return self


class ExtraDataCategoryFieldCreateRequestSchema(MinionExtraDataCategoryField):
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
