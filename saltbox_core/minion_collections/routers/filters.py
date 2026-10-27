from typing import Annotated

from fastapi import APIRouter, Depends

from saltbox_core.minion_collections.schemas.filter import (
    ExtraFilterValuesBody,
    FiltersActions,
    MinionFilterOperatorsSchema,
    MinionFilterSchema,
    MinionFilterValuesBody,
    UniqueValuesResponse,
)
from saltbox_core.minion_collections.schemas.minion import MinionModel
from saltbox_core.minion_collections.services.collection import CollectionService, get_collection_service
from saltbox_core.minion_collections.services.extra_data import ExtraDataService, get_extra_data_service
from saltbox_core.minion_collections.services.extra_data_category import (
    ExtraDataCategoryService,
    get_extra_data_category_service,
)
from saltbox_core.minion_collections.services.minion import MinionService, get_minion_service
from saltbox_core.utilities.model_schema import get_model_schema, schema_lookups_js_values
from saltbox_sdk.discovery_client.schemas import GatewayEndpointConfig
from saltbox_sdk.exceptions import ObjectNotFoundException

router = APIRouter(prefix='/filters', tags=['Filters'])


@router.get(
    '/schema',
    operation_id='filter_schema',
    openapi_extra=GatewayEndpointConfig(
        policy='core.filters.get_schema',
        action=FiltersActions.GET_SCHEMA,
    ).model_dump(by_alias=True),
)
async def filter_schema(
    extra_data_category_service: Annotated[ExtraDataCategoryService, Depends(get_extra_data_category_service)],
) -> list[MinionFilterSchema]:
    schema = [MinionFilterSchema(**field) for field in get_model_schema(MinionModel) if field['name'] != 'extra']
    schema.append(
        MinionFilterSchema(
            name='collection',
            label='Collection',
            operators=[MinionFilterOperatorsSchema(**schema_lookups_js_values[lookup]) for lookup in ('in', 'notIn')],
            input_type='text',
            case_sensitive=True,
        )
    )
    schema.extend(await extra_data_category_service.get_minion_filter_schema())

    return schema


@router.post(
    '/unique-grain-values',
    operation_id='filter_values',
    openapi_extra=GatewayEndpointConfig(
        policy='core.filters.unique_grain_values',
        action=FiltersActions.UNIQUE_GRAIN_VALUES,
    ).model_dump(by_alias=True),
)
async def unique_field_values(
    body: MinionFilterValuesBody,
    collection_service: Annotated[CollectionService, Depends(get_collection_service)],
    minion_service: Annotated[MinionService, Depends(get_minion_service)],
) -> UniqueValuesResponse:
    """Get unique values for a field in the Minion model"""
    collection = await collection_service.get_by_slug(body.collection_slug)

    return await minion_service.get_unique_grain_values(
        field=body.field,
        query={'$and': [collection.full_query, body.query]},
        skip=body.skip,
        limit=body.limit,
    )


@router.post(
    '/unique-extra-values',
    operation_id='filter_extra_values',
    openapi_extra=GatewayEndpointConfig(
        policy='core.filters.unique_extra_values',
        action=FiltersActions.UNIQUE_EXTRA_VALUES,
    ).model_dump(by_alias=True),
)
async def unique_extra_field_values(
    body: ExtraFilterValuesBody,
    collection_service: Annotated[CollectionService, Depends(get_collection_service)],
    extra_data_category_service: Annotated[ExtraDataCategoryService, Depends(get_extra_data_category_service)],
    extra_data_service: Annotated[ExtraDataService, Depends(get_extra_data_service)],
) -> UniqueValuesResponse:
    """Get unique values for a field of an extra data category"""
    collection = await collection_service.get_by_slug(body.collection_slug)

    try:
        category = await extra_data_category_service.get_by_id_or_source_and_name(
            body.category_id, body.category_source, body.category_name
        )
    except ObjectNotFoundException:
        return UniqueValuesResponse(total=0, data=[])

    return await extra_data_service.get_unique_values(
        category,
        body.field,
        query={'$and': [collection.full_query, body.query]},
        skip=body.skip,
        limit=body.limit,
    )
