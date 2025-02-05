from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException

from fastms_core.config import logger
from fastms_core.db.exceptions import ObjectNotFoundError
from fastms_core.db.mongo.schemas_base import PaginatedResponse, PyObjectId
from fastms_core.minion_collections.schemas.minion_schemas import MinionListbody, MinionModel, MinionShortSchema
from fastms_core.minion_collections.services.authz import MinionCollectionAuthzService, get_authz_service
from fastms_core.minion_collections.services.collection_service import CollectionService, get_collection_service
from fastms_core.minion_collections.services.minion_service import MinionService, get_minion_service
from fastms_core.utilities.helpers import recursive_replace_dates

router = APIRouter(prefix='/minions', tags=['Minions'])


@router.post('', operation_id='minions_list')
async def minions_list(
    body: Annotated[MinionListbody, Body()],
    authz_service: Annotated[MinionCollectionAuthzService, Depends(get_authz_service)],
    minion_service: Annotated[MinionService, Depends(get_minion_service)],
    collection_service: Annotated[CollectionService, Depends(get_collection_service)],
) -> PaginatedResponse[MinionShortSchema]:
    authz_result = await authz_service.check_access(
        input={
            'user': authz_service.user.model_dump(),
            'path': ['collections', body.collection_slug],
            'method': 'GET',
            'action': 'retrieve',
        }
    )
    if not authz_result.allow:
        raise HTTPException(status_code=403, detail='Not enough permissions')

    # HOTFIX for last_activity
    search = body.query
    for field_name in ['last_activity']:
        if field_name in search.keys():
            vals = search[field_name]
            for k, v in vals.items():
                if v == '$$FIVE_MINUTES_AGO':
                    vals[k] = datetime.now(UTC) - timedelta(minutes=5)
                else:
                    vals[k] = datetime.fromisoformat(v)

    try:
        collection = await collection_service.get_by_slug(body.collection_slug)
        query = {'$and': [recursive_replace_dates(collection.query), recursive_replace_dates(search)]}
        resp = await minion_service.get_paginated(query=query, skip=body.skip, limit=body.limit)
        return resp
    except ObjectNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except Exception as e:
        logger.error('Error: %s', e)
        raise HTTPException(status_code=500, detail='Something went wrong... See logs') from e


@router.get('/{id}')
async def minion_retrieve(
    collection_slug: str,
    id: PyObjectId,
    authz_service: Annotated[MinionCollectionAuthzService, Depends(get_authz_service)],
    minion_service: Annotated[MinionService, Depends(get_minion_service)],
    collection_service: Annotated[CollectionService, Depends(get_collection_service)],
) -> MinionModel:
    authz_result = await authz_service.check_access(
        input={
            'user': authz_service.user.model_dump(),
            'path': ['collections', collection_slug],
            'method': 'GET',
            'action': 'retrieve',
        }
    )
    if not authz_result.allow:
        raise HTTPException(status_code=403, detail='Not enough permissions')

    try:
        collection = await collection_service.get_by_slug(collection_slug)
    except ObjectNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except Exception as e:
        logger.error('Error: %s', e)
        raise HTTPException(status_code=500, detail='Something went wrong... See logs') from e

    ids = await minion_service.get_ids_by_query(query=collection.query)
    if id not in [i.id for i in ids]:
        raise HTTPException(status_code=404, detail='Minion not found')

    return await minion_service.get(id)
