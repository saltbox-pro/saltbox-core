import json
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status

from saltbox_core.config import logger
from saltbox_core.minion_collections.schemas.collection_schemas import (
    CollectionActions,
    CollectionCreateRequestSchema,
    CollectionCreateSchema,
    CollectionDetailSchema,
    CollectionModel,
    CollectionUpdateSchema,
)
from saltbox_core.minion_collections.services.collection_service import CollectionService, get_collection_service
from saltbox_sdk.db.schemas_base import PaginatedResponse, SkipLimitParams, UserShort
from saltbox_sdk.discovery_client.schemas import GatewayEndpointConfig, OPAQueryFilterFormat
from saltbox_sdk.fastapi_utils.dependencies import get_current_user

router = APIRouter(prefix='/collections', tags=['Minion Collections'])


@router.get(
    '',
    operation_id='minion_collections_list',
    openapi_extra=GatewayEndpointConfig(
        policy='core.collections',
        is_partial=True,
        partial_query='allow == true',
        unknowns=['collections'],
        query_filter_format=OPAQueryFilterFormat.MONGO,
        action=CollectionActions.LIST,
        cache_ttl=0,
    ).model_dump(by_alias=True),  # need to use by_alias=True to match the OpenAPI schema format
)
async def collections_list(
    request: Request,
    params: Annotated[SkipLimitParams, Query()],
    collection_service: Annotated[CollectionService, Depends(get_collection_service)],
) -> PaginatedResponse[CollectionModel]:
    query_str = request.query_params.get('opa_query', None)
    query = json.loads(query_str) if query_str else {}
    logger.info(f'OPA query: {query}')

    return await collection_service.get_list_paginated(query=query, skip=params.skip, limit=params.limit)


@router.get(
    '/default',
    operation_id='minion_collection_default',
    openapi_extra=GatewayEndpointConfig(
        policy='core.collections',
        is_partial=True,
        partial_query='allow == true',
        unknowns=['collections'],
        query_filter_format=OPAQueryFilterFormat.MONGO,
        action=CollectionActions.READ,
        cache_ttl=0,
    ).model_dump(by_alias=True),
)
async def collection_default(
    request: Request,
    collection_service: Annotated[CollectionService, Depends(get_collection_service)],
) -> CollectionDetailSchema:
    query_str = request.query_params.get('opa_query', None)
    query = json.loads(query_str) if query_str else {}
    logger.info(f'Query string: {query_str}')

    logger.info(f'OPA query: {query}')
    response = await collection_service.get(query=query)
    return CollectionDetailSchema(**{**response.model_dump(), '_id': response.id, 'allowed_actions': []})


@router.get(
    '/{slug}',
    operation_id='minion_collection_read',
    openapi_extra=GatewayEndpointConfig(
        policy='core.collections',
        is_partial=False,
        action=CollectionActions.READ,
        cache_ttl=0,
    ).model_dump(by_alias=True),
)
async def collection_retrieve(
    slug: str,
    collection_service: Annotated[CollectionService, Depends(get_collection_service)],
) -> CollectionDetailSchema:
    query = {'slug': slug}
    logger.info(f'OPA query: {query}')
    response = await collection_service.get(query=query)
    logger.info(f'Collection retrieved: {response}')
    return CollectionDetailSchema(**{**response.model_dump(), '_id': response.id, 'allowed_actions': []})


@router.post(
    '',
    operation_id='minion_collection_create',
    openapi_extra=GatewayEndpointConfig(
        policy='core.col',
        # resource='collections',
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
    creation_data['owner'] = user.sub

    return await collection_service.create(CollectionCreateSchema.model_validate(creation_data))


@router.put('/{slug}', operation_id='minion_collection_update')
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
)
async def collection_delete(
    slug: str,
    collection_service: Annotated[CollectionService, Depends(get_collection_service)],
) -> Response:
    await collection_service.delete_by_slug(slug)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
