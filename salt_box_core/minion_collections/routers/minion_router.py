from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import FileResponse

from salt_box_core.config import logger
from salt_box_core.db.exceptions import ObjectNotFoundError
from salt_box_core.db.mongo.schemas_base import PaginatedResponse, PyObjectId
from salt_box_core.minion_collections.schemas.minion_schemas import (
    MinionDetailSchema,
    MinionListbody,
    MinionShortSchema,
)
from salt_box_core.minion_collections.services.authz import MinionCollectionAuthzService, get_authz_service
from salt_box_core.minion_collections.services.collection_service import CollectionService, get_collection_service
from salt_box_core.minion_collections.services.minion_service import MinionService, get_minion_service
from salt_box_core.utilities.helpers import recursive_replace_dates

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

        if collection.query and search:
            query = {'$and': [recursive_replace_dates(collection.query), recursive_replace_dates(search)]}
        else:
            query = recursive_replace_dates(collection.query) if collection.query else recursive_replace_dates(search)

        logger.debug('query: %s', query)

        resp = await minion_service.get_list_paginated(
            query=query, skip=body.skip, limit=body.limit, projection_model=MinionShortSchema
        )
        return resp
    except ObjectNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except Exception as e:
        logger.error('Error: %s', e)
        raise HTTPException(status_code=500, detail='Something went wrong... See logs') from e


@router.post('/export', operation_id='minions_export', response_class=FileResponse)
async def minions_export(
    body: Annotated[MinionListbody, Body()],
    authz_service: Annotated[MinionCollectionAuthzService, Depends(get_authz_service)],
    minion_service: Annotated[MinionService, Depends(get_minion_service)],
    collection_service: Annotated[CollectionService, Depends(get_collection_service)],
) -> FileResponse:
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

    try:
        collection = await collection_service.get_by_slug(body.collection_slug)

        if collection.query and body.query:
            query = {'$and': [recursive_replace_dates(collection.query), recursive_replace_dates(body.query)]}
        else:
            query = (
                recursive_replace_dates(collection.query) if collection.query else recursive_replace_dates(body.query)
            )

        logger.debug('query: %s', query)
        file_path = await minion_service.export_to_csv(query=query, skip=body.skip, limit=body.limit)
        if not file_path:
            raise HTTPException(status_code=404, detail='No data found')
        headers = {'Content-Disposition': f'attachment; filename={file_path.split("/")[-1]}'}
        return FileResponse(
            file_path,
            filename=file_path.split('/')[-1],
            media_type='text/csv',
            headers=headers,
        )
    except ObjectNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except Exception as e:
        logger.error('Error: %s', e)
        raise HTTPException(status_code=500, detail='Something went wrong... See logs') from e


@router.get('/{mid}')
async def minion_retrieve(
    collection_slug: str,
    mid: PyObjectId,
    authz_service: Annotated[MinionCollectionAuthzService, Depends(get_authz_service)],
    minion_service: Annotated[MinionService, Depends(get_minion_service)],
    collection_service: Annotated[CollectionService, Depends(get_collection_service)],
) -> MinionDetailSchema:
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

    ids = await minion_service.get_ids_by_query(query=recursive_replace_dates(collection.query))
    if mid not in [i.id for i in ids]:
        raise HTTPException(status_code=404, detail='Minion not found')

    return await minion_service.get(mid, projection_model=MinionDetailSchema)
