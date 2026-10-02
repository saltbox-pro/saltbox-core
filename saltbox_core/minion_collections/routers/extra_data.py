from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query, Response, status
from fastapi.responses import StreamingResponse

from saltbox_core.minion_collections.schemas.extra_data import (
    CollectionExtraDataListItemSchema,
    ExtraDataActions,
    ExtraDataListItemSchema,
    StaticExtraDataItemCreateRequestSchema,
    StaticExtraDataItemSchema,
    StaticExtraDataItemsCreateResponseSchema,
    StaticExtraDataItemUpdateRequestSchema,
)
from saltbox_core.minion_collections.schemas.extra_data_category import (
    CollectionExtraDataListBody,
    CollectionExtraDataQueryBody,
    ExtraDataCategoryActions,
    ExtraDataCategoryCreateRequestSchema,
    ExtraDataCategoryCreateSchema,
    ExtraDataCategoryListBody,
    ExtraDataCategoryModel,
    ExtraDataCategoryUpdateSchema,
    ExtraDataListBody,
    MinionExtraDataQueryBody,
)
from saltbox_core.minion_collections.schemas.minion import MinionTgtOnlySchema
from saltbox_core.minion_collections.services.collection import CollectionService, get_collection_service
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
) -> PaginatedResponse[ExtraDataListItemSchema]:
    collection = await collection_service.get_by_slug(body.collection_slug) if body.collection_slug else None
    minion = await minion_service.get_in_collection(body.minion_id, collection, projection_model=MinionTgtOnlySchema)
    category = await category_service.get_by_id_or_source_and_name(
        body.category_id, body.category_source, body.category_name
    )

    return await minion_service.get_paginated_extra_data_list(
        query={'minion_id': minion.minion_id, 'master': minion.master},
        category_source=category.source,
        category_name=category.name,
        category_type=category.type,
        field_names=[field.name for field in category.fields],
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
    minion_service: MinionServiceDep,
    category_service: ExtraDataCategoryServiceDep,
    collection_service: CollectionServiceDep,
) -> PaginatedResponse[CollectionExtraDataListItemSchema]:
    collection = await collection_service.get_by_id_or_slug(body.collection_id, body.collection_slug)
    category = await category_service.get_by_id_or_source_and_name(
        body.category_id, body.category_source, body.category_name
    )

    return await minion_service.get_paginated_grouped_extra_data_list(
        group_by_fields=category.category_fields,
        query=collection.full_query,
        category_source=category.source,
        category_name=category.name,
        category_type=category.type,
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
) -> StreamingResponse:
    collection = await collection_service.get_by_slug(body.collection_slug) if body.collection_slug else None
    minion = await minion_service.get_in_collection(body.minion_id, collection, projection_model=MinionTgtOnlySchema)
    category = await category_service.get_by_id_or_source_and_name(
        body.category_id, body.category_source, body.category_name
    )
    field_names = [field.name for field in category.fields]

    rows = minion_service.iter_extra_data_list(
        query={'minion_id': minion.minion_id, 'master': minion.master},
        category_source=category.source,
        category_name=category.name,
        category_type=category.type,
        field_names=field_names,
        search_str=body.search,
        sort=body.sort,
    )
    columns = [(name, name) for name in field_names] + [('updated_at', 'updated_at')]

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
    minion_service: MinionServiceDep,
    category_service: ExtraDataCategoryServiceDep,
    collection_service: CollectionServiceDep,
) -> StreamingResponse:
    collection = await collection_service.get_by_id_or_slug(body.collection_id, body.collection_slug)
    category = await category_service.get_by_id_or_source_and_name(
        body.category_id, body.category_source, body.category_name
    )

    rows = minion_service.iter_grouped_extra_data_list(
        group_by_fields=category.category_fields,
        query=collection.full_query,
        category_source=category.source,
        category_name=category.name,
        category_type=category.type,
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
    item: StaticExtraDataItemCreateRequestSchema,
    category_service: ExtraDataCategoryServiceDep,
    minion_service: MinionServiceDep,
) -> StaticExtraDataItemsCreateResponseSchema:
    category = await category_service.get_manual_static_category(item.category_source, item.category_name)
    data = category_service.clean_manual_data(category, item.data)

    created_items = await minion_service.add_static_extra_data_items(
        item.minion_ids, item.category_source, item.category_name, data, replace_manual=category.is_single_item
    )

    return StaticExtraDataItemsCreateResponseSchema.model_validate(
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
    item: StaticExtraDataItemUpdateRequestSchema,
    category_service: ExtraDataCategoryServiceDep,
    minion_service: MinionServiceDep,
) -> StaticExtraDataItemSchema:
    category = await category_service.get_manual_static_category(item.category_source, item.category_name)
    data = category_service.clean_manual_data(category, item.data)

    updated_item = await minion_service.update_static_extra_data_item(
        item.minion_id, item.category_source, item.category_name, item_id, data
    )

    return StaticExtraDataItemSchema.model_validate(updated_item)


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
    minion_service: MinionServiceDep,
) -> Response:
    await category_service.get_manual_static_category(category_source, category_name)
    await minion_service.delete_static_extra_data_item(minion_id, category_source, category_name, item_id)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
