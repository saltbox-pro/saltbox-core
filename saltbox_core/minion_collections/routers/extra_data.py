from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query, Response, status
from fastapi.responses import StreamingResponse

from saltbox_core.minion_collections.schemas.extra_data import (
    CollectionExtraDataListItemSchema,
    ExtraDataActions,
    ExtraDataItemCreateRequestSchema,
    ExtraDataItemSchema,
    ExtraDataItemsCreateResponseSchema,
    ExtraDataItemUpdateRequestSchema,
    ExtraDataListItemSchema,
)
from saltbox_core.minion_collections.schemas.extra_data_category import (
    CollectionExtraDataListBody,
    CollectionExtraDataQueryBody,
    ExtraDataCategoryActions,
    ExtraDataCategoryCreateRequestSchema,
    ExtraDataCategoryCreateSchema,
    ExtraDataCategoryFieldCreateRequestSchema,
    ExtraDataCategoryFieldsOrderRequestSchema,
    ExtraDataCategoryListBody,
    ExtraDataCategoryModel,
    ExtraDataCategoryUpdateSchema,
    ExtraDataListBody,
    MinionExtraDataQueryBody,
)
from saltbox_core.minion_collections.schemas.minion import MinionTgtOnlySchema
from saltbox_core.minion_collections.services.collection import CollectionService, get_collection_service
from saltbox_core.minion_collections.services.extra_data import ExtraDataService, get_extra_data_service
from saltbox_core.minion_collections.services.extra_data_category import (
    ExtraDataCategoryService,
    get_extra_data_category_service,
)
from saltbox_core.minion_collections.services.minion import MinionService, get_minion_service
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.db.schemas_base import PaginatedResponse
from saltbox_sdk.discovery_client.schemas import GatewayEndpointConfig
from saltbox_sdk.fastapi_utils.csv_export import csv_response

router = APIRouter(prefix='/extra-data', tags=['Extra Data'])

ExtraDataCategoryServiceDep = Annotated[ExtraDataCategoryService, Depends(get_extra_data_category_service)]
ExtraDataServiceDep = Annotated[ExtraDataService, Depends(get_extra_data_service)]
MinionServiceDep = Annotated[MinionService, Depends(get_minion_service)]
CollectionServiceDep = Annotated[CollectionService, Depends(get_collection_service)]


# Categories


@router.post(
    '/categories/list',
    operation_id='extra_data_categories_list',
    openapi_extra=GatewayEndpointConfig(
        policy='core.extra_data.categories.list',
        action=ExtraDataCategoryActions.LIST,
        cache_ttl=0,
    ).model_dump(by_alias=True),
)
async def extra_data_categories_list(
    body: Annotated[ExtraDataCategoryListBody, Body()],
    category_service: ExtraDataCategoryServiceDep,
) -> PaginatedResponse[ExtraDataCategoryModel]:
    query = body.query
    if body.source is not None:
        query = {'$and': [query, {'source': body.source}]}

    return await category_service.get_list_paginated(
        query=query, limit=body.limit, skip=body.skip, sort=body.sort, projection_model=ExtraDataCategoryModel
    )


@router.post(
    '/categories',
    operation_id='extra_data_category_create',
    openapi_extra=GatewayEndpointConfig(
        policy='core.extra_data.categories.create',
        action=ExtraDataCategoryActions.CREATE,
    ).model_dump(by_alias=True),
)
async def extra_data_category_create(
    item: ExtraDataCategoryCreateRequestSchema,
    category_service: ExtraDataCategoryServiceDep,
) -> ExtraDataCategoryModel:
    data = ExtraDataCategoryCreateSchema(
        **item.model_dump(), source='manual', is_system=False, is_manual_data_allowed=True
    )
    category_id = await category_service.create(data=data)

    return await category_service.get(query=category_id)


@router.patch(
    '/categories/{source}/{name}',
    operation_id='extra_data_category_update',
    openapi_extra=GatewayEndpointConfig(
        policy='core.extra_data.categories.update',
        action=ExtraDataCategoryActions.UPDATE,
    ).model_dump(by_alias=True),
)
async def extra_data_category_update(
    source: str,
    name: str,
    item: ExtraDataCategoryUpdateSchema,
    category_service: ExtraDataCategoryServiceDep,
) -> ExtraDataCategoryModel:
    query = {'source': source, 'name': name}
    await category_service.update(query=query, data=item)

    return await category_service.get(query=query)


@router.delete(
    '/categories/{source}/{name}',
    operation_id='extra_data_category_delete',
    status_code=status.HTTP_204_NO_CONTENT,
    openapi_extra=GatewayEndpointConfig(
        policy='core.extra_data.categories.delete',
        action=ExtraDataCategoryActions.DELETE,
    ).model_dump(by_alias=True),
)
async def extra_data_category_delete(
    source: str,
    name: str,
    category_service: ExtraDataCategoryServiceDep,
) -> Response:
    await category_service.delete(query={'source': source, 'name': name})

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    '/categories/{source}/{name}/fields',
    operation_id='extra_data_category_field_create',
    openapi_extra=GatewayEndpointConfig(
        policy='core.extra_data.categories.update',
        action=ExtraDataCategoryActions.UPDATE,
    ).model_dump(by_alias=True),
)
async def extra_data_category_field_create(
    source: str,
    name: str,
    field: ExtraDataCategoryFieldCreateRequestSchema,
    category_service: ExtraDataCategoryServiceDep,
) -> ExtraDataCategoryModel:
    await category_service.add_field(source, name, field)

    return await category_service.get(query={'source': source, 'name': name})


@router.delete(
    '/categories/{source}/{name}/fields/{field_name}',
    operation_id='extra_data_category_field_delete',
    openapi_extra=GatewayEndpointConfig(
        policy='core.extra_data.categories.update',
        action=ExtraDataCategoryActions.UPDATE,
    ).model_dump(by_alias=True),
)
async def extra_data_category_field_delete(
    source: str,
    name: str,
    field_name: str,
    category_service: ExtraDataCategoryServiceDep,
) -> ExtraDataCategoryModel:
    await category_service.delete_field(source, name, field_name)

    return await category_service.get(query={'source': source, 'name': name})


@router.post(
    '/categories/{source}/{name}/fields/order',
    operation_id='extra_data_category_fields_order',
    openapi_extra=GatewayEndpointConfig(
        policy='core.extra_data.categories.update',
        action=ExtraDataCategoryActions.UPDATE,
    ).model_dump(by_alias=True),
)
async def extra_data_category_fields_order(
    source: str,
    name: str,
    body: ExtraDataCategoryFieldsOrderRequestSchema,
    category_service: ExtraDataCategoryServiceDep,
) -> ExtraDataCategoryModel:
    await category_service.set_fields_order(source, name, body.field_names)

    return await category_service.get(query={'source': source, 'name': name})


# Items


@router.post(
    '/items/by-minion',
    operation_id='extra_data_items_by_minion',
    openapi_extra=GatewayEndpointConfig(
        policy='core.extra_data.items.by_minion',
        action=ExtraDataActions.LIST,
        cache_ttl=0,
    ).model_dump(by_alias=True),
)
async def extra_data_items_by_minion(
    body: Annotated[ExtraDataListBody, Body()],
    minion_service: MinionServiceDep,
    category_service: ExtraDataCategoryServiceDep,
    collection_service: CollectionServiceDep,
    extra_data_service: ExtraDataServiceDep,
) -> PaginatedResponse[ExtraDataListItemSchema]:
    collection = await collection_service.get_by_slug(body.collection_slug) if body.collection_slug else None
    minion = await minion_service.get_in_collection(body.minion_id, collection, projection_model=MinionTgtOnlySchema)
    category = await category_service.get_by_id_or_source_and_name(
        body.category_id, body.category_source, body.category_name
    )

    return await extra_data_service.get_minion_items_paginated(
        category,
        query={'minion_id': minion.minion_id, 'master': minion.master},
        search_str=body.search,
        limit=body.limit,
        skip=body.skip,
        sort=body.sort,
    )


@router.post(
    '/items/by-collection',
    operation_id='extra_data_items_by_collection',
    openapi_extra=GatewayEndpointConfig(
        policy='core.extra_data.items.by_collection',
        action=ExtraDataActions.LIST,
        cache_ttl=0,
    ).model_dump(by_alias=True),
)
async def extra_data_items_by_collection(
    body: Annotated[CollectionExtraDataListBody, Body()],
    category_service: ExtraDataCategoryServiceDep,
    collection_service: CollectionServiceDep,
    extra_data_service: ExtraDataServiceDep,
) -> PaginatedResponse[CollectionExtraDataListItemSchema]:
    collection = await collection_service.get_by_id_or_slug(body.collection_id, body.collection_slug)
    category = await category_service.get_by_id_or_source_and_name(
        body.category_id, body.category_source, body.category_name
    )

    return await extra_data_service.get_grouped_items_paginated(
        category,
        query=collection.full_query,
        search_str=body.search,
        limit=body.limit,
        skip=body.skip,
        sort=body.sort,
    )


@router.post(
    '/items/by-minion/export',
    operation_id='extra_data_items_by_minion_export',
    response_class=StreamingResponse,
    openapi_extra=GatewayEndpointConfig(
        policy='core.extra_data.items.by_minion',
        action=ExtraDataActions.EXPORT,
        cache_ttl=0,
    ).model_dump(by_alias=True),
)
async def extra_data_items_by_minion_export(
    body: Annotated[MinionExtraDataQueryBody, Body()],
    minion_service: MinionServiceDep,
    category_service: ExtraDataCategoryServiceDep,
    collection_service: CollectionServiceDep,
    extra_data_service: ExtraDataServiceDep,
) -> StreamingResponse:
    collection = await collection_service.get_by_slug(body.collection_slug) if body.collection_slug else None
    minion = await minion_service.get_in_collection(body.minion_id, collection, projection_model=MinionTgtOnlySchema)
    category = await category_service.get_by_id_or_source_and_name(
        body.category_id, body.category_source, body.category_name
    )

    rows = extra_data_service.iter_minion_items(
        category,
        query={'minion_id': minion.minion_id, 'master': minion.master},
        search_str=body.search,
        sort=body.sort,
    )
    columns = [(field.name, field.name) for field in category.fields] + [('updated_at', 'updated_at')]

    return csv_response(columns, rows, ['extra_data', category.source, category.name, minion.minion_id])


@router.post(
    '/items/by-collection/export',
    operation_id='extra_data_items_by_collection_export',
    response_class=StreamingResponse,
    openapi_extra=GatewayEndpointConfig(
        policy='core.extra_data.items.by_collection',
        action=ExtraDataActions.EXPORT,
        cache_ttl=0,
    ).model_dump(by_alias=True),
)
async def extra_data_items_by_collection_export(
    body: Annotated[CollectionExtraDataQueryBody, Body()],
    category_service: ExtraDataCategoryServiceDep,
    collection_service: CollectionServiceDep,
    extra_data_service: ExtraDataServiceDep,
) -> StreamingResponse:
    collection = await collection_service.get_by_id_or_slug(body.collection_id, body.collection_slug)
    category = await category_service.get_by_id_or_source_and_name(
        body.category_id, body.category_source, body.category_name
    )

    rows = extra_data_service.iter_grouped_items(
        category,
        query=collection.full_query,
        search_str=body.search,
        sort=body.sort,
    )
    columns = [(name, name) for name in category.category_fields] + [('minions_count', '_minions_count')]

    return csv_response(columns, rows, ['extra_data', category.source, category.name, collection.slug or ''])


@router.post(
    '/items',
    operation_id='extra_data_item_create',
    openapi_extra=GatewayEndpointConfig(
        policy='core.extra_data.items.create',
        action=ExtraDataActions.CREATE,
    ).model_dump(by_alias=True),
)
async def extra_data_item_create(
    item: ExtraDataItemCreateRequestSchema,
    category_service: ExtraDataCategoryServiceDep,
    extra_data_service: ExtraDataServiceDep,
) -> ExtraDataItemsCreateResponseSchema:
    category = await category_service.get_manual_data_category(item.category_source, item.category_name)

    created_items = await extra_data_service.add_items(category, item.minion_ids, item.data, is_system=False)

    return ExtraDataItemsCreateResponseSchema.model_validate(
        {'minions_count': len(created_items), 'items': created_items}
    )


@router.put(
    '/items/{item_id}',
    operation_id='extra_data_item_update',
    openapi_extra=GatewayEndpointConfig(
        policy='core.extra_data.items.update',
        action=ExtraDataActions.UPDATE,
    ).model_dump(by_alias=True),
)
async def extra_data_item_update(
    item_id: PyObjectId,
    item: ExtraDataItemUpdateRequestSchema,
    category_service: ExtraDataCategoryServiceDep,
    extra_data_service: ExtraDataServiceDep,
) -> ExtraDataItemSchema:
    category = await category_service.get_manual_data_category(item.category_source, item.category_name)

    updated_item = await extra_data_service.update_item(category, item.minion_id, item_id, item.data)

    return ExtraDataItemSchema.model_validate(updated_item)


@router.delete(
    '/items/{item_id}',
    operation_id='extra_data_item_delete',
    status_code=status.HTTP_204_NO_CONTENT,
    openapi_extra=GatewayEndpointConfig(
        policy='core.extra_data.items.delete',
        action=ExtraDataActions.DELETE,
    ).model_dump(by_alias=True),
)
async def extra_data_item_delete(
    item_id: PyObjectId,
    category_source: Annotated[str, Query()],
    category_name: Annotated[str, Query()],
    minion_id: Annotated[PyObjectId, Query()],
    category_service: ExtraDataCategoryServiceDep,
    extra_data_service: ExtraDataServiceDep,
) -> Response:
    category = await category_service.get_manual_data_category(category_source, category_name)
    await extra_data_service.delete_item(category, minion_id, item_id)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
