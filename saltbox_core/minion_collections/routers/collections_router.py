from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Response, status

from saltbox_core.config import logger
from saltbox_core.minion_collections.schemas.collection_schemas import (
    CollectionActions,
    CollectionCreateRequestSchema,
    CollectionCreateSchema,
    CollectionDetailSchema,
    CollectionListBody,
    CollectionModel,
    CollectionTreeNodeSchema,
    CollectionUpdateSchema,
)
from saltbox_core.minion_collections.services.collection_service import CollectionService, get_collection_service
from saltbox_sdk.db.schemas_base import PaginatedResponse, UserShort
from saltbox_sdk.discovery_client.schemas import GatewayEndpointConfig
from saltbox_sdk.fastapi_utils.dependencies import get_current_user, get_opa_query

router = APIRouter(prefix='/collections', tags=['Minion Collections'])


@router.post(
    '/list',
    operation_id='minion_collections_list',
    openapi_extra=GatewayEndpointConfig(
        policy='core.collections.list',
        action=CollectionActions.LIST,
        cache_ttl=0,
    ).model_dump(by_alias=True),  # need to use by_alias=True to match the OpenAPI schema format
)
async def collections_list(
    params: Annotated[CollectionListBody, Body()],
    opa_query: Annotated[dict, Depends(get_opa_query)],
    collection_service: Annotated[CollectionService, Depends(get_collection_service)],
) -> PaginatedResponse[CollectionModel]:
    logger.info(f'OPA query: {opa_query}')

    query: dict[str, Any] = {}
    queries: list[dict[str, Any]] = []

    if opa_query:
        queries.append(opa_query)
    if params.query:
        queries.append(params.query)

    if len(queries) == 1:
        query = queries[0]
    elif len(queries) > 1:
        query = {'$and': queries}

    return await collection_service.get_list_paginated(
        query=query,
        skip=params.skip,
        limit=params.limit,
        sort=params.sort,
    )


@router.post(
    '/tree',
    operation_id='minion_collections_tree',
    openapi_extra=GatewayEndpointConfig(
        policy='core.collections.list',
        action=CollectionActions.LIST,
        cache_ttl=0,
    ).model_dump(by_alias=True),  # need to use by_alias=True to match the OpenAPI schema format
)
async def collections_tree(
    opa_query: Annotated[dict, Depends(get_opa_query)],
    collection_service: Annotated[CollectionService, Depends(get_collection_service)],
) -> list[CollectionTreeNodeSchema]:
    logger.info(f'OPA query: {opa_query}')

    return await collection_service.get_tree(query=opa_query, projection_model=CollectionTreeNodeSchema)


@router.get(
    '/default',
    operation_id='minion_collection_default',
    openapi_extra=GatewayEndpointConfig(
        policy='core.collections.default',
        action=CollectionActions.READ,
        cache_ttl=0,
    ).model_dump(by_alias=True),
)
async def collection_default(
    opa_query: Annotated[dict, Depends(get_opa_query)],
    collection_service: Annotated[CollectionService, Depends(get_collection_service)],
) -> CollectionDetailSchema:
    logger.info(f'OPA query: {opa_query}')

    response = await collection_service.get_list(query=opa_query, limit=1, skip=0)
    return CollectionDetailSchema(**{**response[0].model_dump(), '_id': response[0].id, 'allowed_actions': []})


@router.get(
    '/{slug}',
    operation_id='minion_collection_read',
    openapi_extra=GatewayEndpointConfig(
        policy='core.collections.read',
        action=CollectionActions.READ,
        cache_ttl=0,
    ).model_dump(by_alias=True),
)
async def collection_retrieve(
    slug: str,
    collection_service: Annotated[CollectionService, Depends(get_collection_service)],
) -> CollectionDetailSchema:
    response = await collection_service.get(query={'slug': slug})
    return CollectionDetailSchema(**{**response.model_dump(), '_id': response.id, 'allowed_actions': []})


@router.post(
    '',
    operation_id='minion_collection_create',
    openapi_extra=GatewayEndpointConfig(
        policy='core.collections.create',
        action=CollectionActions.CREATE,
    ).model_dump(by_alias=True),
)
async def collection_create(
    collection: CollectionCreateRequestSchema,
    user: Annotated[UserShort, Depends(get_current_user)],
    collection_service: Annotated[CollectionService, Depends(get_collection_service)],
) -> CollectionModel:
    creation_data = collection.model_dump()
    parent_slug = creation_data.pop('parent_slug')

    parent_collection = await collection_service.get_by_slug(parent_slug)
    creation_data['parent_id'] = parent_collection.id
    creation_data['owner_id'] = user.sub

    return await collection_service.create(CollectionCreateSchema.model_validate(creation_data))


@router.put(
    '/{slug}',
    operation_id='minion_collection_update',
    openapi_extra=GatewayEndpointConfig(
        policy='core.collections.update',
        action=CollectionActions.UPDATE,
    ).model_dump(by_alias=True),
)
async def collection_update(
    slug: str,
    collection: CollectionUpdateSchema,
    collection_service: Annotated[CollectionService, Depends(get_collection_service)],
) -> CollectionDetailSchema:
    response = await collection_service.update_by_slug(slug, collection)
    # TODO (a.baikov): Add allowed actions to response
    return CollectionDetailSchema(**{**response.model_dump(), '_id': response.id, 'allowed_actions': []})


@router.delete(
    '/{slug}',
    operation_id='minion_collection_delete',
    status_code=status.HTTP_204_NO_CONTENT,
    openapi_extra=GatewayEndpointConfig(
        policy='core.collections.delete',
        action=CollectionActions.DELETE,
    ).model_dump(by_alias=True),
)
async def collection_delete(
    slug: str,
    collection_service: Annotated[CollectionService, Depends(get_collection_service)],
) -> Response:
    await collection_service.delete_by_slug(slug)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
