from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from salt_box_core.config import logger
from salt_box_core.db.exceptions import DuplicateKeyError, ObjectCreateError, ObjectNotFoundError, ObjectUpdateError
from salt_box_core.db.schemas_base import PaginatedResponse, SkipLimitParams
from salt_box_core.minion_collections.schemas.collection_schemas import (
    CollectionCreateSchema,
    CollectionDetailSchema,
    CollectionModel,
    CollectionUpdateSchema,
)
from salt_box_core.minion_collections.services.authz import MinionCollectionAuthzService, get_authz_service
from salt_box_core.minion_collections.services.collection_service import CollectionService, get_collection_service

router = APIRouter(prefix='/collections', tags=['Minion Collections'])


@router.get('', operation_id='minion_collections_list')
async def collections_list(
    params: Annotated[SkipLimitParams, Query()],
    authz_service: Annotated[MinionCollectionAuthzService, Depends(get_authz_service)],
    collection_service: Annotated[CollectionService, Depends(get_collection_service)],
) -> PaginatedResponse[CollectionModel]:
    authz_result = await authz_service.check_access(action='retrieve')
    if not authz_result.allow:
        raise HTTPException(status_code=403, detail='Not enough permissions')

    query = None if authz_result.is_admin else {'slug': {'$in': authz_result.allowed_slugs}}

    try:
        return await collection_service.get_list_paginated(query=query, skip=params.skip, limit=params.limit)
    except Exception as e:
        logger.error('Error: %s', e)
        raise HTTPException(status_code=500, detail='Something went wrong... See logs') from e


# TODO (a.baikov): Find another way to get default collection
@router.get('/default', operation_id='minion_collection_default')
async def collection_default(
    authz_service: Annotated[MinionCollectionAuthzService, Depends(get_authz_service)],
    collection_service: Annotated[CollectionService, Depends(get_collection_service)],
) -> CollectionDetailSchema:
    """Retern `root` collection if user has access to it, otherwise return first allowed collection"""
    slug = 'root'
    authz_result = await authz_service.check_access(
        input={
            'user': authz_service.user.model_dump(),
            'path': ['collections', slug],
            'method': 'GET',
            'action': 'retrieve',
        }
    )
    if not authz_result.allow and authz_result.allowed_slugs:
        slug = authz_result.allowed_slugs[0]
        authz_result = await authz_service.check_access(
            input={
                'user': authz_service.user.model_dump(),
                'path': ['collections', slug],
                'method': 'GET',
                'action': 'retrieve',
            }
        )
    else:
        raise HTTPException(status_code=403, detail='You does not have access to any collection')

    try:
        response = await collection_service.get_by_slug(slug)
        return CollectionDetailSchema(
            **{**response.model_dump(), '_id': response.id, 'allowed_actions': authz_result.allowed_actions}
        )
    except Exception as e:
        logger.error('Error: %s', e)
        raise HTTPException(status_code=500, detail='Something went wrong... See logs') from e


@router.get('/{slug}', operation_id='minion_collection_read')
async def collection_retrieve(
    slug: str,
    authz_service: Annotated[MinionCollectionAuthzService, Depends(get_authz_service)],
    collection_service: Annotated[CollectionService, Depends(get_collection_service)],
) -> CollectionDetailSchema:
    authz_result = await authz_service.check_access(action='retrieve')
    if not authz_result.allow:
        raise HTTPException(status_code=403, detail='Not enough permissions')

    try:
        response = await collection_service.get_by_slug(slug)
        return CollectionDetailSchema(
            **{**response.model_dump(), '_id': response.id, 'allowed_actions': authz_result.allowed_actions}
        )
    except ObjectNotFoundError:
        raise HTTPException(status_code=404, detail='Collection not found') from None
    except Exception as e:
        logger.error('Error: %s', e)
        raise HTTPException(status_code=500, detail='Something went wrong... See logs') from e


@router.post('', operation_id='minion_collection_create')
async def collection_create(
    collection: CollectionCreateSchema,
    authz_service: Annotated[MinionCollectionAuthzService, Depends(get_authz_service)],
    collection_service: Annotated[CollectionService, Depends(get_collection_service)],
) -> CollectionModel:
    allow = await authz_service.allow('create')
    if not allow:
        raise HTTPException(status_code=403, detail='Not enough permissions')

    try:
        return await collection_service.create(collection)
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
    authz_service: Annotated[MinionCollectionAuthzService, Depends(get_authz_service)],
    collection_service: Annotated[CollectionService, Depends(get_collection_service)],
) -> CollectionDetailSchema:
    authz_result = await authz_service.check_access(action='retrieve')
    if not authz_result.allow:
        raise HTTPException(status_code=403, detail='Not enough permissions')

    try:
        response = await collection_service.update_by_slug(slug, collection)
        return CollectionDetailSchema(
            **{**response.model_dump(), '_id': response.id, 'allowed_actions': authz_result.allowed_actions}
        )
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
    authz_service: Annotated[MinionCollectionAuthzService, Depends(get_authz_service)],
    collection_service: Annotated[CollectionService, Depends(get_collection_service)],
) -> Response:
    allow = await authz_service.allow('delete')
    if not allow:
        raise HTTPException(status_code=403, detail='Not enough permissions')

    try:
        await collection_service.delete_by_slug(slug)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except ObjectNotFoundError:
        raise HTTPException(status_code=404, detail='Collection not found') from None
    except Exception as e:
        logger.error('Error: %s', e)
        raise HTTPException(status_code=500, detail='Something went wrong... See logs') from e
