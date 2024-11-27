from __future__ import annotations

import logging.config
from inspect import isclass
from types import GenericAlias
from typing import get_args

from pydantic import BaseModel

from fastms_core.config import LOG_CONFIG

logging.config.dictConfig(LOG_CONFIG.model_dump())

logger = logging.getLogger(__name__)


class UnsupportedSchemaType(Exception):
    pass


def get_model_schema(model: type[BaseModel], pre_path: str | None = None) -> list[dict[str, str]]:
    schema = []

    for field_name, field in model.model_fields.items():
        full_field_name = f'{pre_path}.{field_name}' if pre_path else field_name

        sub_model: type[BaseModel] | None = None

        print(field_name)
        try:
            for field_class in get_args(field.annotation):
                if isinstance(field_class, GenericAlias):
                    if field_class.__origin__ in [dict, list]:
                        raise UnsupportedSchemaType
                if isclass(field_class) and issubclass(field_class, BaseModel):
                    sub_model = field_class
                    break
        except UnsupportedSchemaType:
            continue
        print('\n')

        if sub_model:
            schema.extend(get_model_schema(sub_model, full_field_name))
        else:
            schema.append(
                {
                    'name': full_field_name,
                    'label': field.title if field.title else full_field_name,
                }
            )

    return schema
