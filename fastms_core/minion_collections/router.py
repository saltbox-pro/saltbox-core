import logging.config
from typing import Annotated

import httpx
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from fastms_core.config import LOG_CONFIG, SETTINGS
from fastms_core.db.mongo.schemas_base import PaginatedListParams, User
from fastms_core.dependencies import get_current_user  # , get_current_user_from_jwt
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
async def clients_list(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
) -> list[MinionCollectionSchema]:
    logger.info('user: %s', user.model_dump())
    repository = CollectionRepository()
    path_list = request.url.path.split('/')[3:]
    logger.info('path_list: %s', path_list)
    input_dict = {
        'input': {
            'user': user.model_dump(),
            'path': path_list,
            'method': request.method,
            'action': 'retrieve',
        }
    }
    async with httpx.AsyncClient() as r:
        response = await r.post(f'{SETTINGS.opa_url}/v1/data/core/collections', json=input_dict)
        response.raise_for_status()
        response_json = response.json()
        logger.info('response_json: %s', response_json)
        if not response_json['result'] or not response_json['result']['allow']:
            raise HTTPException(status_code=403, detail='Forbidden access')

    query = {'slug': {'$in': response_json['result']['allowed_slugs']}}
    return await repository.find_all(query)


@router.get('/{slug}', operation_id='minion_collection_read', response_model_by_alias=False)
async def clients_read(
    request: Request,
    slug: str,
    params: Annotated[PaginatedListParams, Query()],
    user: Annotated[User, Depends(get_current_user)],
) -> MinionCollectionDetailSchema:
    collections_repo = CollectionRepository()
    client = await collections_repo.get_by_slug_protected(slug, user, request)

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
        client.query, page=params.page, per_page=params.per_page, projection_query=projection_query
    )

    client.minions = minions.data
    client.total = minions.total

    return client


@router.get('/{slug}/{mid}', operation_id='minion_collection_read_minion', response_model_by_alias=False)
async def clients_read_minion(
    request: Request,
    slug: str,
    mid: str,
    user: Annotated[User, Depends(get_current_user)],
) -> MinionSchema:
    collections_repo = CollectionRepository()
    client = await collections_repo.get_by_slug_protected(slug, user, request)

    minions_repo = MinionRepository()
    query = {
        '$and': [
            client.query,
            {'_id': ObjectId(mid)},
        ]
    }
    minion = await minions_repo.find_one(query)
    if not minion:
        raise HTTPException(status_code=404, detail='Minion not found')

    return minion


@router.post('', operation_id='minion_collection_create', response_model_by_alias=False)
async def clients_create(
    collection: MinionCollectionCreateSchema,
    user: Annotated[User, Depends(get_current_user)],
) -> MinionCollectionSchema:
    repository = CollectionRepository()
    logger.debug('user: %s', user)
    created = await repository.add(collection)
    if not created:
        raise HTTPException(status_code=400, detail='Collection not created')
    return created
