from typing import Annotated

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query

# from fastms_core.config import logger
from fastms_core.db.mongo.schemas_base import PaginatedListParams, PaginatedResponse
from fastms_core.minion_collections.repository import CollectionRepository, MinionRepository
from fastms_core.minion_collections.schemas.collection_schemas import (
    MinionCollectionCreateSchema,
    MinionCollectionDetailBody,
    MinionCollectionDetailSchema,
    MinionCollectionListSchema,
    MinionCollectionSchema,
)
from fastms_core.minion_collections.schemas.minion_schemas import MinionSchema
from fastms_core.minion_collections.services.authz import MinionCollectionAuthzService, get_authz_service
from fastms_core.minion_collections.services.collection_service import MinionCollectionService, get_collection_service

router = APIRouter(prefix='/collections', tags=['Minion Collections'])


@router.get('', operation_id='minion_collections_list', response_model_by_alias=False)
async def collections_list(
    params: Annotated[PaginatedListParams, Query()],
    authz_service: Annotated[MinionCollectionAuthzService, Depends(get_authz_service)],
    collection_service: Annotated[MinionCollectionService, Depends(get_collection_service)],
) -> PaginatedResponse[MinionCollectionListSchema]:
    authz_result = await authz_service.check_access(action='retrieve')
    if not authz_result.allow:
        raise HTTPException(status_code=403, detail='Not enough permissions')

    if authz_result.is_admin:
        response = await collection_service.get_list({}, page=params.page, per_page=params.per_page)
    else:
        response = await collection_service.get_list(
            {'slug': {'$in': authz_result.allowed_slugs}}, page=params.page, per_page=params.per_page
        )
    return response


# TODO (a.baikov): Find another way to get default collection
@router.post('/default', operation_id='minion_collection_default', response_model_by_alias=False)
async def collection_default(
    body: MinionCollectionDetailBody,
    authz_service: Annotated[MinionCollectionAuthzService, Depends(get_authz_service)],
    collection_service: Annotated[MinionCollectionService, Depends(get_collection_service)],
) -> MinionCollectionDetailSchema:
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
    if not authz_result.allow:
        slug = authz_result.allowed_slugs[0]
        authz_result = await authz_service.check_access(
            input={
                'user': authz_service.user.model_dump(),
                'path': ['collections', slug],
                'method': 'GET',
                'action': 'retrieve',
            }
        )

    response = await collection_service.get_by_slug(slug, query=body.query, page=body.page, per_page=body.per_page)

    response.allowed_actions = authz_result.allowed_actions

    return response


@router.post('/{slug}', operation_id='minion_collection_read', response_model_by_alias=False)
async def collection_retrieve(
    slug: str,
    body: MinionCollectionDetailBody,
    authz_service: Annotated[MinionCollectionAuthzService, Depends(get_authz_service)],
    collection_service: Annotated[MinionCollectionService, Depends(get_collection_service)],
) -> MinionCollectionDetailSchema:
    authz_result = await authz_service.check_access(action='retrieve')
    if not authz_result.allow:
        raise HTTPException(status_code=403, detail='Not enough permissions')

    response = await collection_service.get_by_slug(slug, query=body.query, page=body.page, per_page=body.per_page)

    response.allowed_actions = authz_result.allowed_actions

    return response


@router.get('/{slug}/{mid}', operation_id='minion_collection_read_minion', response_model_by_alias=False)
async def collection_minion_retrieve(
    slug: str,
    mid: str,
    authz_service: Annotated[MinionCollectionAuthzService, Depends(get_authz_service)],
) -> MinionSchema:
    allow = await authz_service.allow('retrieve')
    if not allow:
        raise HTTPException(status_code=403, detail='Not enough permissions')

    collections_repo = CollectionRepository()
    collection = await collections_repo.find_one({'slug': slug})
    if not collection:
        raise HTTPException(status_code=404, detail='Collection not found')

    minions_repo = MinionRepository()
    query = {
        '$and': [
            collection.query,
            {'_id': ObjectId(mid)},
        ]
    }
    minion = await minions_repo.find_one(query)
    if not minion:
        raise HTTPException(status_code=404, detail='Minion not found')

    return minion


@router.post('', operation_id='minion_collection_create', response_model_by_alias=False)
async def collection_create(
    collection: MinionCollectionCreateSchema,
    authz_service: Annotated[MinionCollectionAuthzService, Depends(get_authz_service)],
    collection_service: Annotated[MinionCollectionService, Depends(get_collection_service)],
) -> MinionCollectionSchema:
    allow = await authz_service.allow('create')
    if not allow:
        raise HTTPException(status_code=403, detail='Not enough permissions')

    created = await collection_service.create(collection)

    return created
