from __future__ import annotations

import logging

from pydantic import BaseModel

from fastms_core.config import LOG_CONFIG
from fastms_core.minions.schemas import GrainsSchema

logging.config.dictConfig(LOG_CONFIG.model_dump())

logger = logging.getLogger(__name__)


def get_model_schema(model: type[BaseModel], pre_path: str | None = None) -> list[dict[str, str]]:
    schema = []

    for field_name, field in model.model_fields.items():
        full_field_name = f'{pre_path}.{field_name}' if pre_path else field_name

        if field_name == 'grains':
            schema.extend(get_model_schema(GrainsSchema, full_field_name))
        else:
            schema.append(
                {
                    'name': full_field_name,
                    'label': field.title if field.title else full_field_name,
                }
            )

    return schema
