import logging.config
from typing import Annotated

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query

from fastms_core.config import LOG_CONFIG
from fastms_core.db.mongo.schemas_base import PaginatedListParams
from fastms_core.minion_collections.authz import MinionCollectionAuthzService, get_authz_service
from fastms_core.minion_collections.repository import CollectionRepository, MinionRepository
from fastms_core.minion_collections.schemas import (
    MinionCollectionCreateSchema,
    MinionCollectionDetailSchema,
    MinionCollectionSchema,
    MinionSchema,
)

logging.config.dictConfig(LOG_CONFIG.model_dump())

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/collections', tags=['Minion Collections'])


@router.get('', operation_id='minion_collections_list', response_model_by_alias=False)
async def collections_list(
    params: Annotated[PaginatedListParams, Query()],
    authz_service: Annotated[MinionCollectionAuthzService, Depends(get_authz_service)],
) -> list[MinionCollectionSchema]:
    logger.debug('user: %s', authz_service.user.model_dump())

    authz_result = await authz_service.check_access('retrieve')
    if not authz_result.allow:
        raise HTTPException(status_code=403, detail='Not enough permissions')

    repository = CollectionRepository()
    query = {'slug': {'$in': authz_result.allowed_slugs}}
    return await repository.find_all(query)


@router.get('/{slug}', operation_id='minion_collection_read', response_model_by_alias=False)
async def collection_retrieve(
    slug: str,
    params: Annotated[PaginatedListParams, Query()],
    authz_service: Annotated[MinionCollectionAuthzService, Depends(get_authz_service)],
) -> MinionCollectionDetailSchema:
    logger.debug('user: %s', authz_service.user.model_dump())

    authz_result = await authz_service.check_access('retrieve')
    if not authz_result.allow:
        if slug != 'root':
            raise HTTPException(status_code=403, detail='Not enough permissions')

        # TODO (a.baikov): in this case we get first allowed collection, but without allowed actions
        # need to implement a separate endpoint for root collection or move all logic to service layer
        slug = authz_result.allowed_slugs[0]

    collections_repo = CollectionRepository()
    collection = await collections_repo.find_one({'slug': slug})
    if not collection:
        raise HTTPException(status_code=404, detail='Collection not found')

    minions_repo = MinionRepository()
    projection_query = {
        'minion_id': 1,
        'master': 1,
        'grains.id': 1,
        'grains.fqdn': 1,
        'grains.osfullname': 1,
        'grains.domain': 1,
        'grains.efi': 1,
        'grains.cpu_model': 1,
        'grains.mem_total': 1,
        'created': 1,
        'modified': 1,
    }

    minions = await minions_repo.get_paginated(
        collection.query, page=params.page, per_page=params.per_page, projection_query=projection_query
    )

    return MinionCollectionDetailSchema(
        **collection.model_dump(),
        allowed_actions=authz_result.allowed_actions,
        minions={**minions},
    )


@router.get('/{slug}/{mid}', operation_id='minion_collection_read_minion', response_model_by_alias=False)
async def collection_minion_retrieve(
    slug: str,
    mid: str,
    authz_service: Annotated[MinionCollectionAuthzService, Depends(get_authz_service)],
) -> MinionSchema:
    logger.debug('user: %s', authz_service.user.model_dump())
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
) -> MinionCollectionSchema:
    logger.debug('user: %s', authz_service.user)
    allow = await authz_service.allow('create')
    if not allow:
        raise HTTPException(status_code=403, detail='Not enough permissions')

    repository = CollectionRepository()
    created = await repository.add(collection)
    if not created:
        raise HTTPException(status_code=400, detail='Collection not created')
    return created
