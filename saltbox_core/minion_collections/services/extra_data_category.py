from typing import Annotated, Any

from fastapi import Depends

from saltbox_core.minion_collections.repositories.extra_data_category import (
    ExtraDataCategoryRepository,
    get_extra_data_category_repository,
)
from saltbox_core.minion_collections.schemas.extra_data_category import (
    ExtraDataCategoryCreateSchema,
    ExtraDataCategoryModel,
    ExtraDataCategoryUpdateSchema,
)
from saltbox_core.minion_collections.schemas.filter import MinionFilterOperatorsSchema, MinionFilterSchema
from saltbox_core.utilities.model_schema import (
    schema_input_type_map,
    schema_lookups_js_values,
    schema_lookups_map,
    schema_nullable_lookups,
    schema_text_lookups,
)
from saltbox_sdk.db.mongo.schemas_base import EmptyModel, PyObjectId
from saltbox_sdk.event_bus.schemas import MinionExtraDataCategoryFieldType
from saltbox_sdk.serivces.mongo_base_service import MongoBaseService


class ExtraDataCategoryService(
    MongoBaseService[
        ExtraDataCategoryRepository,
        ExtraDataCategoryModel,
        ExtraDataCategoryCreateSchema,
        ExtraDataCategoryUpdateSchema,
    ]
):
    async def get_minion_filter_schema_for_category(self, category_id: PyObjectId) -> list[MinionFilterSchema]:
        category = await self.get(category_id)
        schema: list[MinionFilterSchema] = []

        for field in category.fields:
            field_schema_lookups: list[str] = []
            field_schema_type: str | None = None

            for field_type in field.types:
                if field_type == MinionExtraDataCategoryFieldType.NONE:
                    field_schema_lookups.extend(schema_nullable_lookups)
                else:
                    field_schema_lookups.extend(
                        [
                            lookup
                            for lookup in schema_lookups_map.get(field_type.python_type, schema_text_lookups)
                            if lookup not in field_schema_lookups
                        ]
                    )
                    field_schema_type = schema_input_type_map.get(field_type.python_type, None)

            field_schema_lookups_computed = [
                MinionFilterOperatorsSchema(**schema_lookups_js_values[lookup]) for lookup in field_schema_lookups
            ]

            field_schema: dict[str, Any] = {
                'name': f'extra.{category.source}.{category.name}.{field.name}',
                'label': f'Extra data field "{category.source}.{category.name}.{field.name}"',
                'operators': field_schema_lookups_computed,
            }

            if field_schema_type == 'checkbox':
                field_schema['value_editor_type'] = field_schema_type
                field_schema['default_value'] = False
            else:
                field_schema['input_type'] = field_schema_type

            schema.append(MinionFilterSchema(**field_schema))

        return schema

    async def get_minion_filter_schema(self) -> list[MinionFilterSchema]:
        schema: list[MinionFilterSchema] = []
        categories = await self.get_list(query={}, projection_model=EmptyModel)

        for category in categories:
            schema.extend(await self.get_minion_filter_schema_for_category(category.id))

        return schema


def get_extra_data_category_service(
    repo: Annotated[ExtraDataCategoryRepository, Depends(get_extra_data_category_repository)],
) -> ExtraDataCategoryService:
    return ExtraDataCategoryService(repo)
