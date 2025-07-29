import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from saltbox_core.config import logger
from saltbox_core.minion_collections.schemas.collection_schemas import (
    CollectionCreateRequestSchema,
    CollectionCreateSchema,
    CollectionDetailSchema,
    CollectionModel,
    CollectionUpdateSchema,
)
from saltbox_core.minion_collections.services.collection_service import CollectionService, get_collection_service
from saltbox_sdk.db.exceptions import (
    DuplicateKeyError,
    ObjectCreateError,
    ObjectDeleteError,
    ObjectNotFoundError,
    ObjectUpdateError,
)
from saltbox_sdk.db.schemas_base import PaginatedResponse, SkipLimitParams
from saltbox_sdk.discovery_client.schemas import GatewayEndpointConfig, OPAQueryFilterFormat

router = APIRouter(prefix='/collections', tags=['Minion Collections'])


@router.get(
    '',
    operation_id='minion_collections_list',
    openapi_extra=GatewayEndpointConfig(
        policy='core.col',
        is_partial=True,
        partial_query='allow == true',
        unknowns=['collections'],
        query_filter_format=OPAQueryFilterFormat.MONGO,
        action='list',
        cache_ttl=60,
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
    '/{slug}',
    operation_id='minion_collection_read',
    openapi_extra={
        'x-opa-policy': 'core.col',
        'x-opa-partial': True,
        'x-opa-query': 'allow == true',
        'x-opa-unknowns': ['collections'],
        'x-opa-query-filter-format': 'mongo',
        'x-cache-ttl': 5,
    },
)
async def collection_retrieve(
    request: Request,
    slug: str,
    collection_service: Annotated[CollectionService, Depends(get_collection_service)],
) -> CollectionDetailSchema:
    query_str = request.query_params.get('opa_query', None)
    query = json.loads(query_str) if query_str else {}
    logger.info(f'Query string: {query_str}')

    if slug == 'default':
        allowed_collections = await collection_service.get_list(query=query, limit=1, skip=0)
        logger.info(f'Allowed collections: {allowed_collections}')
        if not allowed_collections:
            raise HTTPException(status_code=404, detail='No collections found')

        return CollectionDetailSchema(
            **{**allowed_collections[0].model_dump(), '_id': allowed_collections[0].id, 'allowed_actions': []}
        )

    query = {**query, 'slug': slug}
    logger.info(f'OPA query: {query}')
    try:
        response = await collection_service.get(query=query)
        return CollectionDetailSchema(**{**response.model_dump(), '_id': response.id, 'allowed_actions': []})
    except ObjectNotFoundError:
        raise HTTPException(status_code=404, detail='Collection not found') from None
    except Exception as e:
        logger.error('Error: %s', e)
        raise HTTPException(status_code=500, detail='Something went wrong... See logs') from e


@router.post('', operation_id='minion_collection_create')
async def collection_create(
    collection: CollectionCreateRequestSchema,
    collection_service: Annotated[CollectionService, Depends(get_collection_service)],
) -> CollectionModel:
    creation_data = collection.model_dump()
    parent_slug = creation_data.pop('parent_slug')

    try:
        parent_collection = await collection_service.get_by_slug(parent_slug)
        creation_data['parent_id'] = parent_collection.id
    except ObjectNotFoundError as e:
        raise HTTPException(status_code=404, detail='Parent collection not found') from e

    try:
        return await collection_service.create(CollectionCreateSchema.model_validate(creation_data))
    except ObjectCreateError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except DuplicateKeyError as e:
        msg = f'Collection with slug `{collection.slug}` already exists'
        raise HTTPException(status_code=400, detail=msg) from e
    except Exception as e:
        logger.error('Error: %s', e)
        raise HTTPException(status_code=500, detail='Something went wrong... See logs') from e


@router.put('/{slug}', operation_id='minion_collection_update')
async def collection_update(
    slug: str,
    collection: CollectionUpdateSchema,
    collection_service: Annotated[CollectionService, Depends(get_collection_service)],
) -> CollectionDetailSchema:
    try:
        response = await collection_service.update_by_slug(slug, collection)
        # TODO (a.baikov): Add allowed actions to response
        return CollectionDetailSchema(**{**response.model_dump(), '_id': response.id, 'allowed_actions': []})
    except ObjectUpdateError:
        raise HTTPException(status_code=404, detail='Collection not found') from None
    except Exception as e:
        logger.error('Error: %s', e)
        raise HTTPException(status_code=500, detail='Something went wrong... See logs') from e


@router.delete(
    '/{slug}',
    operation_id='minion_collection_delete',
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        204: {'description': 'No Content'},
        403: {'description': 'Forbidden'},
        404: {'description': 'Not Found'},
        422: {'description': 'Unprocessable Entity'},
    },
)
async def collection_delete(
    slug: str,
    collection_service: Annotated[CollectionService, Depends(get_collection_service)],
) -> Response:
    try:
        await collection_service.delete_by_slug(slug)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except ObjectNotFoundError as e:
        raise HTTPException(status_code=404, detail='Collection not found') from e
    except ObjectDeleteError as e:
        raise HTTPException(status_code=400, detail=e.detail) from e
    except Exception as e:
        logger.error('Error: %s', e)
        raise HTTPException(status_code=500, detail='Something went wrong... See logs') from e
