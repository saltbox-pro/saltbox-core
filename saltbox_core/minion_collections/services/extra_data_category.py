from typing import Annotated, Any

from fastapi import Depends
from pymongo.asynchronous.client_session import AsyncClientSession as MongoAsyncClientSession

from saltbox_core.minion_collections.repositories.extra_data_category import (
    ExtraDataCategoryRepository,
    get_extra_data_category_repository,
)
from saltbox_core.minion_collections.schemas.extra_data_category import (
    ExtraDataCategoryCreateSchema,
    ExtraDataCategoryFieldCreateRequestSchema,
    ExtraDataCategoryModel,
    ExtraDataCategoryUpdateSchema,
)
from saltbox_core.minion_collections.schemas.filter import MinionFilterOperatorsSchema, MinionFilterSchema
from saltbox_core.minion_collections.services.extra_data import ExtraDataService, get_extra_data_service
from saltbox_core.utilities.model_schema import (
    schema_input_type_map,
    schema_lookups_js_values,
    schema_lookups_map,
    schema_nullable_lookups,
    schema_text_lookups,
)
from saltbox_sdk.db.mongo.repository_base import MongoUpdateOperator
from saltbox_sdk.db.mongo.schemas_base import EmptyModel, PyObjectId
from saltbox_sdk.event_bus.schemas import MinionExtraDataCategoryFieldType
from saltbox_sdk.exceptions import ObjectNotFoundException, PermissionDeniedException, SaltBoxValidationException
from saltbox_sdk.serivces.mongo_base_service import MongoBaseService


class ExtraDataCategoryService(
    MongoBaseService[
        ExtraDataCategoryRepository,
        ExtraDataCategoryModel,
        ExtraDataCategoryCreateSchema,
        ExtraDataCategoryUpdateSchema,
    ]
):
    def __init__(
        self,
        repo: ExtraDataCategoryRepository,
        extra_data_service: ExtraDataService,
    ) -> None:
        super().__init__(repo)
        self.extra_data_service = extra_data_service

    async def update(
        self,
        query: dict[str, Any] | PyObjectId,
        data: ExtraDataCategoryUpdateSchema | dict[str, Any],
        exclude_unset: bool = True,
        *,
        operator: MongoUpdateOperator = MongoUpdateOperator.set,
        session: MongoAsyncClientSession | None = None,
    ) -> PyObjectId:
        await self.get_editable_category(query, session=session)

        return await super().update(query, data, exclude_unset, operator=operator, session=session)

    async def get_editable_category(
        self, query: dict[str, Any] | PyObjectId, *, session: MongoAsyncClientSession | None = None
    ) -> ExtraDataCategoryModel:
        category = await self.get(query, session=session)
        if category.is_system:
            msg = 'System-managed categories cannot be edited manually.'
            raise PermissionDeniedException(msg)

        return category

    async def add_field(self, source: str, name: str, field: ExtraDataCategoryFieldCreateRequestSchema) -> None:
        await self.get_editable_category({'source': source, 'name': name})

        result = await self.repo.push_field(
            source,
            name,
            field.model_dump(exclude={'is_minion_field'}),
            is_minion_field=field.is_minion_field,
        )
        if result.matched_count == 0:
            msg = f'Field `{field.name}` already exists'
            raise SaltBoxValidationException(msg)

    async def delete_field(self, source: str, name: str, field_name: str) -> None:
        category = await self.get_editable_category({'source': source, 'name': name})

        if field_name not in [field.name for field in category.fields]:
            raise ObjectNotFoundException(obj_type='extra_data_category_field', query={'name': field_name})

        await self.extra_data_service.remove_category_field(category, field_name)

        result = await self.repo.pull_field(source, name, field_name)
        if result.matched_count == 0:
            raise ObjectNotFoundException(obj_type='extra_data_category_field', query={'name': field_name})

    async def set_fields_order(self, source: str, name: str, field_names: list[str]) -> None:
        await self.get_editable_category({'source': source, 'name': name})

        result = await self.repo.set_fields_order(source, name, field_names)
        if result.matched_count == 0:
            msg = 'Fields order contains unknown category fields.'
            raise SaltBoxValidationException(msg)

    async def delete(
        self,
        query: dict[str, Any] | PyObjectId,
        *,
        session: MongoAsyncClientSession | None = None,
    ) -> int:
        category = await self.get(query, session=session)
        if category.is_system:
            msg = 'System-managed categories cannot be deleted manually.'
            raise PermissionDeniedException(msg)

        await self.extra_data_service.remove_category_data(category)

        return await super().delete(query, session=session)

    async def get_by_id_or_source_and_name(
        self, category_id: PyObjectId | None, source: str | None, name: str | None
    ) -> ExtraDataCategoryModel:
        if category_id is not None:
            return await self.get(query=category_id)

        return await self.get(query={'source': source, 'name': name})

    async def get_manual_data_category(self, source: str, name: str) -> ExtraDataCategoryModel:
        category = await self.get(query={'source': source, 'name': name})

        if not category.is_manual_data_allowed:
            msg = 'Manual data entries are not allowed for this category.'
            raise PermissionDeniedException(msg)

        return category

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
    extra_data_service: Annotated[ExtraDataService, Depends(get_extra_data_service)],
) -> ExtraDataCategoryService:
    return ExtraDataCategoryService(repo, extra_data_service=extra_data_service)
