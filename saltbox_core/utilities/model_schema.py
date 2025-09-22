import types
from datetime import datetime
from inspect import isclass
from typing import Any, get_args
from uuid import UUID

from pydantic import BaseModel
from pydantic.fields import ComputedFieldInfo, FieldInfo

from saltbox_core.config import logger
from saltbox_core.exceptions import UnsupportedSchemaTypeException
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.utilities.helpers import Iso8601ZDatetime as TimezoneAwareDatetime

# TODO (a.baikov): remove this in new version querybuilder
TEMP_EXCLUDE_FIELDS_LIST = [
    'id',
    'gpus',
    'dns',
    'hwaddr_interfaces',
    'ip4_interfaces',
    'ip6_interfaces',
    'ip_interfaces',
    'kernelparams',
    'locale_info',
    'pythonversion',
    'saltversioninfo',
]
schema_lookups_js_values = {
    '=': {'name': '=', 'value': '=', 'label': '='},
    '!=': {'name': '!=', 'value': '!=', 'label': '!='},
    '<': {'name': '<', 'value': '<', 'label': '<'},
    '>': {'name': '>', 'value': '>', 'label': '>'},
    '<=': {'name': '<=', 'value': '<=', 'label': '<='},
    '>=': {'name': '>=', 'value': '>=', 'label': '>='},
    'contains': {'name': 'contains', 'value': 'contains', 'label': 'contains'},
    'beginsWith': {'name': 'beginsWith', 'value': 'beginsWith', 'label': 'begins with'},
    'endsWith': {'name': 'endsWith', 'value': 'endsWith', 'label': 'ends with'},
    'doesNotContain': {'name': 'doesNotContain', 'value': 'doesNotContain', 'label': 'does not contain'},
    'doesNotBeginWith': {'name': 'doesNotBeginWith', 'value': 'doesNotBeginWith', 'label': 'does not begin with'},
    'doesNotEndWith': {'name': 'doesNotEndWith', 'value': 'doesNotEndWith', 'label': 'does not end with'},
    'null': {'name': 'null', 'value': 'null', 'label': 'is null'},
    'notNull': {'name': 'notNull', 'value': 'notNull', 'label': 'is not null'},
    'in': {'name': 'in', 'value': 'in', 'label': 'in'},
    'notIn': {'name': 'notIn', 'value': 'notIn', 'label': 'not in'},
    'between': {'name': 'between', 'value': 'between', 'label': 'between'},
    'notBetween': {'name': 'notBetween', 'value': 'notBetween', 'label': 'not between'},
}
schema_all_lookups = [
    '=',
    '!=',
    '<',
    '>',
    '<=',
    '>=',
    'contains',
    'beginsWith',
    'endsWith',
    'doesNotContain',
    'doesNotBeginWith',
    'doesNotEndWith',
    'null',
    'notNull',
    'in',
    'notIn',
    'between',
    'notBetween',
]
schema_number_lookups = ['=', '!=', '<', '>', '<=', '>=', 'between', 'notBetween']
schema_text_lookups = [
    '=',
    '!=',
    'contains',
    'beginsWith',
    'endsWith',
    'doesNotContain',
    'doesNotBeginWith',
    'doesNotEndWith',
    'in',
    'notIn',
]
schema_datetime_lookups = ['<', '>', '<=', '>=']
schema_nullable_lookups = ['null', 'notNull']
schema_lookups_map = {
    int: schema_number_lookups,
    float: schema_number_lookups,
    str: schema_text_lookups,
    bool: ['='],
    list: ['in', 'notIn'],
    datetime: schema_datetime_lookups,
    TimezoneAwareDatetime: schema_datetime_lookups,
    PyObjectId: schema_text_lookups,
    UUID: schema_text_lookups,
}

schema_input_type_map = {
    int: 'number',
    float: 'number',
    str: None,
    bool: 'checkbox',
    PyObjectId: 'text',
    UUID: 'text',
    # datetime: 'datetime-local',
    datetime: 'date',
    TimezoneAwareDatetime: 'date',
}


def get_model_schema(model: type[BaseModel], pre_path: str | None = None) -> list[dict[str, Any]]:
    schema = []
    fields: dict[str, FieldInfo | ComputedFieldInfo] = {}

    fields.update(model.model_fields)
    fields.update(model.model_computed_fields)

    for field_name, field in fields.items():
        if field_name in TEMP_EXCLUDE_FIELDS_LIST:
            continue
        full_field_name = f'{pre_path}.{field_name}' if pre_path else field_name

        sub_model, nullable_field, computed_field_class = analyze_field(field)

        if sub_model:
            schema.extend(get_model_schema(sub_model, full_field_name))
        else:
            schema.append(create_field_schema(full_field_name, field, nullable_field, computed_field_class))

    schema.sort(key=lambda x: x['label'])
    return schema


def analyze_field(field: Any) -> tuple[type[BaseModel] | None, bool, Any]:  # noqa: C901
    sub_model: type[BaseModel] | None = None
    nullable_field: bool = False
    computed_field_class = None

    try:
        if type(field) is FieldInfo:
            field_annotations = get_args(field.annotation)
            field_annotations = (field.annotation,) if not field_annotations else field_annotations
        elif type(field) is ComputedFieldInfo:
            field_annotations = get_args(field.return_type)
            field_annotations = (field.return_type,) if not field_annotations else field_annotations
        else:
            logger.warning(f'Unsupported field type: {type(field)}')
            raise UnsupportedSchemaTypeException()

        for field_class in field_annotations:
            if field_class is type(None):
                nullable_field = True
                continue
            if isinstance(field_class, types.GenericAlias):
                if field_class.__origin__ in [dict, list]:
                    if field_class in [list[str], list[int], list[Any]]:
                        computed_field_class = list
                        continue
                    msg = f'GenericAlias {field_class} not supported for field {field.title}'
                    raise UnsupportedSchemaTypeException(msg)
            if isclass(field_class) and issubclass(field_class, BaseModel):
                sub_model = field_class
                break
            if field_class:
                computed_field_class = field_class

    except UnsupportedSchemaTypeException as e:
        logger.warning(str(e))

    return sub_model, nullable_field, computed_field_class


def create_field_schema(
    full_field_name: str, field: Any, nullable_field: bool, computed_field_class: Any
) -> dict[str, Any]:
    field_schema_lookups: list[str] = schema_lookups_map.get(computed_field_class, schema_text_lookups)
    field_schema_type: str | None = schema_input_type_map.get(computed_field_class, None)

    if nullable_field:
        field_schema_lookups = field_schema_lookups + schema_nullable_lookups

    field_schema_lookups_computed = [schema_lookups_js_values[lookup] for lookup in field_schema_lookups]

    if not field.title:
        logger.debug(f'Field: {full_field_name}, title: {field.title}')
    field_schema = {
        'name': full_field_name,
        'label': field.title if field.title else full_field_name,
        'operators': field_schema_lookups_computed,
    }
    if field_schema_type == 'checkbox':
        field_schema['value_editor_type'] = field_schema_type
        field_schema['default_value'] = False
    else:
        field_schema['input_type'] = field_schema_type

    # TODO (a.baikov): use this for datetime fields
    if full_field_name in ['created', 'modified', 'last_activity']:
        field_schema['value_editor_type'] = 'datetime-local'
        field_schema['input_type'] = 'datetime-local'
        field_schema['datatype'] = 'timestamp with time zone'

    return field_schema
