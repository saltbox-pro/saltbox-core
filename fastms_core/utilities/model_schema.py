from __future__ import annotations

import logging.config
import types
from inspect import isclass
from typing import Any, get_args
from uuid import UUID

from beanie.odm.fields import PydanticObjectId
from pydantic import BaseModel

from fastms_core.config import LOG_CONFIG

logging.config.dictConfig(LOG_CONFIG.model_dump())

logger = logging.getLogger(__name__)


class UnsupportedSchemaType(Exception):
    pass



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
    '=', '!=', '<', '>', '<=', '>=', 'contains', 'beginsWith', 'endsWith', 'doesNotContain',  'doesNotBeginWith',
    'doesNotEndWith', 'null', 'notNull', 'in', 'notIn', 'between', 'notBetween'
]
schema_number_lookups = ['=', '!=', '<', '>', '<=', '>=', 'in', 'notIn']
schema_text_lookups = [
    '=', '!=', 'contains', 'beginsWith', 'endsWith', 'doesNotContain',
    'doesNotBeginWith', 'doesNotEndWith', 'in', 'notIn'
]
schema_nullable_lookups = ['null', 'notNull']
schema_lookups_map = {
    int: schema_number_lookups,
    float: schema_number_lookups,
    str: schema_text_lookups,
    bool: ['=', '!='],
    list: ['in', 'notIn'],
    PydanticObjectId: schema_text_lookups,
    UUID: schema_text_lookups,
}

schema_input_type_map = {
    int: 'number',
    float: 'number',
    str: 'text',
    bool: 'checkbox',
    PydanticObjectId: 'text',
    UUID: 'text',
}


def get_model_schema(model: type[BaseModel], pre_path: str | None = None) -> list[dict[str, Any]]:
    schema = []

    for field_name, field in model.model_fields.items():
        full_field_name = f'{pre_path}.{field_name}' if pre_path else field_name

        sub_model: type[BaseModel] | None = None
        nullable_field: bool = False
        computed_field_class = None

        try:
            for field_class in get_args(field.annotation):
                if field_class is types.NoneType:
                    nullable_field = True
                    continue
                if isinstance(field_class, types.GenericAlias):
                    if field_class.__origin__ in [dict, list]:
                        raise UnsupportedSchemaType
                if isclass(field_class) and issubclass(field_class, BaseModel):
                    sub_model = field_class
                    break
                computed_field_class = field_class
        except UnsupportedSchemaType:
            continue

        if sub_model:
            schema.extend(get_model_schema(sub_model, full_field_name))
        else:
            field_schema_lookups: list[str] = schema_lookups_map.get(computed_field_class, schema_text_lookups)
            field_schema_type: str = schema_input_type_map.get(computed_field_class, 'text')

            if nullable_field:
                field_schema_lookups = field_schema_lookups + schema_nullable_lookups

            field_schema_lookups_computed = [schema_lookups_js_values[lookup] for lookup in field_schema_lookups]

            schema.append(
                {
                    'name': full_field_name,
                    'label': field.title if field.title else full_field_name,
                    'operators': field_schema_lookups_computed,
                    'input_type': field_schema_type,
                }
            )

    return schema
