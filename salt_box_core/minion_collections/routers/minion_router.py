from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Response, status
from fastapi.responses import FileResponse
from pydantic import ValidationError

from salt_box_core.config import logger
from salt_box_core.event_bus.masters_bus import send_message_and_wait_response_to_master
from salt_box_core.masters.schemas.master_schemas import MasterModel
from salt_box_core.masters.services.master_service import MasterService, get_master_service
from salt_box_core.minion_collections.schemas.minion_schemas import (
    MinionDetailSchema,
    MinionListBody,
    MinionShortSchema,
)
from salt_box_core.minion_collections.services.collection_service import CollectionService, get_collection_service
from salt_box_core.minion_collections.services.minion_service import MinionService, get_minion_service
from saltbox_bridge_messages import BridgeGatherMinionsResponse, CoreGatherMinionsRequest, MasterStatus
from saltbox_sdk import http_errors
from saltbox_sdk.db.exceptions import ObjectNotFoundError
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.db.schemas_base import PaginatedResponse

router = APIRouter(prefix='/minions', tags=['Minions'])


@router.post('', operation_id='minions_list')
async def minions_list(
    body: Annotated[MinionListBody, Body()],
    minion_service: Annotated[MinionService, Depends(get_minion_service)],
    collection_service: Annotated[CollectionService, Depends(get_collection_service)],
) -> PaginatedResponse[MinionShortSchema]:
    search = body.query

    try:
        collection = await collection_service.get_by_slug(body.collection_slug)

        if collection.full_query and search:
            query = {'$and': [collection.full_query, search]}
        else:
            query = collection.full_query if collection.full_query else search

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
    body: Annotated[MinionListBody, Body()],
    minion_service: Annotated[MinionService, Depends(get_minion_service)],
    collection_service: Annotated[CollectionService, Depends(get_collection_service)],
) -> FileResponse:
    try:
        collection = await collection_service.get_by_slug(body.collection_slug)

        if collection.full_query and body.query:
            query = {'$and': [collection.full_query, body.query]}
        else:
            query = collection.full_query if collection.full_query else body.query

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


@router.get('/gather')
async def gather_minions(
    tgt: str,
    tgt_type: str,
    master: str,
    master_service: Annotated[MasterService, Depends(get_master_service)],
) -> BridgeGatherMinionsResponse:
    try:
        master_obj: MasterModel = await master_service.get_by_master_id(master)
    except ObjectNotFoundError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err

    if master_obj.status != MasterStatus.ACCEPTED:
        raise HTTPException(status_code=403, detail='Master not accepted')

    try:
        gather_minions_req = CoreGatherMinionsRequest(master=master_obj.master_id, tgt=tgt, tgt_type=tgt_type)
    except ValidationError as err:
        raise http_errors.BadRequest(err.errors()) from err
    minions = await send_message_and_wait_response_to_master(
        message=gather_minions_req,
        message_tag='gather_minions',
        response_timeout=10.0,
    )
    return BridgeGatherMinionsResponse.model_validate(minions)


@router.get('/{mid}')
async def minion_retrieve(
    collection_slug: str,
    mid: PyObjectId,
    minion_service: Annotated[MinionService, Depends(get_minion_service)],
    collection_service: Annotated[CollectionService, Depends(get_collection_service)],
) -> MinionDetailSchema:
    try:
        collection = await collection_service.get_by_slug(collection_slug)
    except ObjectNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except Exception as e:
        logger.error('Error: %s', e)
        raise HTTPException(status_code=500, detail='Something went wrong... See logs') from e

    ids = await minion_service.get_ids_by_query(query=collection.full_query)
    if mid not in [i.id for i in ids]:
        raise HTTPException(status_code=404, detail='Minion not found')

    minion = await minion_service.get(mid)

    # TODO (a.baikov): doing like this because of additional_grains. Need to find a better way
    minion = MinionDetailSchema(**minion.model_dump(exclude={'id'}), _id=minion.id)

    return minion


@router.delete(
    '/{mid}',
    operation_id='minion_delete',
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_204_NO_CONTENT: {'description': 'No Content'},
        status.HTTP_403_FORBIDDEN: {'description': 'Forbidden'},
        status.HTTP_404_NOT_FOUND: {'description': 'Not Found'},
        status.HTTP_422_UNPROCESSABLE_ENTITY: {'description': 'Unprocessable Entity'},
    },
)
async def minion_delete(
    collection_slug: str,
    mid: PyObjectId,
    minion_service: Annotated[MinionService, Depends(get_minion_service)],
    collection_service: Annotated[CollectionService, Depends(get_collection_service)],
) -> Response:
    try:
        collection = await collection_service.get_by_slug(collection_slug)
    except ObjectNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except Exception as e:
        logger.error('Error: %s', e)
        raise HTTPException(status_code=500, detail='Something went wrong... See logs') from e

    ids = await minion_service.get_ids_by_query(query=collection.full_query)
    if mid not in [i.id for i in ids]:
        raise HTTPException(status_code=404, detail='Minion not found')

    try:
        await minion_service.delete(mid)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except ObjectNotFoundError:
        raise HTTPException(status_code=404, detail='Minion not found') from None
    except Exception as e:
        logger.error('Error: %s', e)
        raise HTTPException(status_code=500, detail='Something went wrong... See logs') from e
