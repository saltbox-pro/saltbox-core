from typing import Annotated

from fastapi import APIRouter, Depends

from saltbox_core.minion_collections.schemas.filter import (
    FiltersActions,
    MinionFilterSchema,
    MinionFilterValuesBody,
    UniqueGrainValuesResponse,
)
from saltbox_core.minion_collections.schemas.minion import MinionModel
from saltbox_core.minion_collections.services.collection import CollectionService, get_collection_service
from saltbox_core.minion_collections.services.extra_data_category import (
    ExtraDataCategoryService,
    get_extra_data_category_service,
)
from saltbox_core.minion_collections.services.minion import MinionService, get_minion_service
from saltbox_core.utilities.model_schema import get_model_schema
from saltbox_sdk.discovery_client.schemas import GatewayEndpointConfig

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
    schema = [MinionFilterSchema(**field) for field in get_model_schema(MinionModel)]
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
) -> UniqueGrainValuesResponse:
    """Get unique values for a field in the Minion model"""
    collection = await collection_service.get_by_slug(body.collection_slug)

    if not body.field.startswith('grains.'):
        return UniqueGrainValuesResponse(total=0, data=[])

    query = {'$and': [collection.full_query, body.query]}

    result = await minion_service.get_unique_grain_values_by_field(
        field=body.field,
        query=query,
        skip=body.skip,
        limit=body.limit,
    )

    return result
