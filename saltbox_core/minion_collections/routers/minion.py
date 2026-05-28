from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Response, status
from fastapi.responses import FileResponse

from saltbox_bridge_messages import BridgeGatherMinionsResponse, CoreGatherMinionsRequest, MasterStatus, SaltTgtType
from saltbox_core.config import logger
from saltbox_core.event_bus.redis.masters_bus import send_message_and_wait_response_to_master
from saltbox_core.masters.schemas.master_schemas import MasterModel
from saltbox_core.masters.services.master_service import MasterService, get_master_service
from saltbox_core.minion_collections.schemas.minion import (
    MinionBulkDeleteBody,
    MinionDetailSchema,
    MinionListBody,
    MinionsActions,
    MinionShortSchema,
)
from saltbox_core.minion_collections.services.collection import CollectionService, get_collection_service
from saltbox_core.minion_collections.services.minion import MinionService, get_minion_service
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.db.schemas_base import PaginatedResponse, UserShort
from saltbox_sdk.discovery_client.schemas import GatewayEndpointConfig
from saltbox_sdk.fastapi_utils.dependencies import get_current_user

router = APIRouter(prefix='/minions', tags=['Minions'])


@router.post(
    '',
    operation_id='minions_list',
    openapi_extra=GatewayEndpointConfig(
        policy='core.minions.list',
        action=MinionsActions.LIST,
    ).model_dump(by_alias=True),
)
async def minions_list(
    body: Annotated[MinionListBody, Body()],
    minion_service: Annotated[MinionService, Depends(get_minion_service)],
    collection_service: Annotated[CollectionService, Depends(get_collection_service)],
) -> PaginatedResponse[MinionShortSchema]:
    search = body.query
    collection = await collection_service.get_by_slug(body.collection_slug)

    if collection.full_query and search:
        query = {'$and': [collection.full_query, search]}
    else:
        query = collection.full_query if collection.full_query else search

    return await minion_service.get_list_paginated(
        query=query,
        skip=body.skip,
        limit=body.limit,
        projection_model=MinionShortSchema,
        sort=body.sort,
    )


@router.post(
    '/export',
    operation_id='minions_export',
    openapi_extra=GatewayEndpointConfig(
        policy='core.minions.export',
        action=MinionsActions.EXPORT,
    ).model_dump(by_alias=True),
    response_class=FileResponse,
)
async def minions_export(
    body: Annotated[MinionListBody, Body()],
    minion_service: Annotated[MinionService, Depends(get_minion_service)],
    collection_service: Annotated[CollectionService, Depends(get_collection_service)],
) -> FileResponse:
    collection = await collection_service.get_by_slug(body.collection_slug)

    if collection.full_query and body.query:
        query = {'$and': [collection.full_query, body.query]}
    else:
        query = collection.full_query if collection.full_query else body.query

    file_path = await minion_service.export_to_csv(query=query, skip=body.skip, limit=body.limit)

    headers = {'Content-Disposition': f'attachment; filename={file_path.split("/")[-1]}'}
    return FileResponse(
        file_path,
        filename=file_path.split('/')[-1],
        media_type='text/csv',
        headers=headers,
    )


@router.get(
    '/gather',
    operation_id='minions_gather',
    openapi_extra=GatewayEndpointConfig(
        policy='core.minions.gather',
        action=MinionsActions.GATHER,
    ).model_dump(by_alias=True),
)
async def gather_minions(
    tgt: str,
    tgt_type: SaltTgtType,
    master: str,
    master_service: Annotated[MasterService, Depends(get_master_service)],
) -> BridgeGatherMinionsResponse:
    master_obj: MasterModel = await master_service.get_by_master_id(master)

    if master_obj.status != MasterStatus.ACCEPTED:
        raise HTTPException(status_code=403, detail='Master not accepted')

    gather_minions_req = CoreGatherMinionsRequest(master=master_obj.master_id, tgt=tgt, tgt_type=tgt_type)
    minions = await send_message_and_wait_response_to_master(
        message=gather_minions_req,
        message_tag='gather_minions',
        response_timeout=10.0,
    )
    return BridgeGatherMinionsResponse.model_validate(minions)


@router.get(
    '/{mid}',
    operation_id='minion_get',
    openapi_extra=GatewayEndpointConfig(
        policy='core.minions.read',
        action=MinionsActions.READ,
    ).model_dump(by_alias=True),
)
async def minion_retrieve(
    collection_slug: str,
    mid: PyObjectId,
    minion_service: Annotated[MinionService, Depends(get_minion_service)],
    collection_service: Annotated[CollectionService, Depends(get_collection_service)],
) -> MinionDetailSchema:
    collection = await collection_service.get_by_slug(collection_slug)

    ids = await minion_service.get_ids_by_query(query=collection.full_query)
    if mid not in [i.id for i in ids]:
        raise HTTPException(status_code=404, detail='Minion not found')

    minion = await minion_service.get(mid)

    # TODO (a.baikov): doing like this because of additional_grains. Need to find a better way
    minion = MinionDetailSchema(**minion.model_dump(exclude={'id'}, by_alias=True), _id=minion.id)

    return minion


@router.get(
    '/{master_id}/{minion_id}',
    operation_id='minion_get_by_master_and_id',
    openapi_extra=GatewayEndpointConfig(
        policy='core.minions.read',
        action=MinionsActions.READ,
    ).model_dump(by_alias=True),
)
async def minion_retrieve_by_master_and_id(
    master_id: str,
    minion_id: str,
    minion_service: Annotated[MinionService, Depends(get_minion_service)],
) -> MinionDetailSchema:
    minion = await minion_service.get_by_master_and_id(master=master_id, minion_id=minion_id)

    # TODO (a.baikov): doing like this because of additional_grains. Need to find a better way
    minion = MinionDetailSchema(**minion.model_dump(exclude={'id'}), _id=minion.id)

    return minion


@router.delete(
    '/delete/{mid}',
    operation_id='minion_delete',
    openapi_extra=GatewayEndpointConfig(
        policy='core.minions.delete',
        action=MinionsActions.DELETE,
    ).model_dump(by_alias=True),
    status_code=status.HTTP_204_NO_CONTENT,
)
async def minion_delete(
    collection_slug: str,
    mid: PyObjectId,
    minion_service: Annotated[MinionService, Depends(get_minion_service)],
    collection_service: Annotated[CollectionService, Depends(get_collection_service)],
) -> Response:
    collection = await collection_service.get_by_slug(collection_slug)

    ids = await minion_service.get_ids_by_query(query=collection.full_query)
    if mid not in [i.id for i in ids]:
        raise HTTPException(status_code=404, detail='Minion not found')

    await minion_service.delete(mid)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    '/bulk_delete',
    operation_id='minion_bulk_delete',
    openapi_extra=GatewayEndpointConfig(
        policy='core.minions.delete',
        action=MinionsActions.DELETE,
    ).model_dump(by_alias=True),
    status_code=status.HTTP_204_NO_CONTENT,
)
async def minion_bulk_delete(
    body: Annotated[MinionBulkDeleteBody, Body()],
    user: Annotated[UserShort, Depends(get_current_user)],
    minion_service: Annotated[MinionService, Depends(get_minion_service)],
    collection_service: Annotated[CollectionService, Depends(get_collection_service)],
) -> Response:
    deleted_count = 0
    collection = await collection_service.get_by_slug(body.collection_slug)

    ids = [i.id for i in await minion_service.get_ids_by_query(query=collection.full_query)]
    for mid in body.minions:
        if mid not in ids:
            continue

        deleted_count += await minion_service.delete(mid)

    logger.debug(
        f'Deleted {deleted_count} minions from "{body.collection_slug}" collection '
        f'by {user.name} [{user.email}] ({user.sub})'
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
