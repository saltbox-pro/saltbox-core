from typing import Annotated

from fastapi import APIRouter, Body, Depends, Response, status

# from saltbox_core.config import logger
from saltbox_core.pillars.schemas import (
    PillarCreateRequestSchema,
    PillarCreateSchema,
    PillarListBody,
    PillarModel,
    PillarsActions,
    PillarUpdateSchema,
    PillarWithTgtInfoSchema,
)
from saltbox_core.pillars.services.pillar import PillarService, get_pillar_service
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.db.schemas_base import PaginatedResponse, UserShort
from saltbox_sdk.discovery_client.schemas import GatewayEndpointConfig
from saltbox_sdk.fastapi_utils.dependencies import get_current_user, get_opa_query

router = APIRouter(prefix='/pillars', tags=['Pillars'])


@router.post(
    '',
    operation_id='pillar_create',
    openapi_extra=GatewayEndpointConfig(
        policy='public',
        action=PillarsActions.CREATE,
        cache_ttl=0,
    ).model_dump(by_alias=True),
)
async def pillar_create(
    pillar: PillarCreateRequestSchema,
    pillar_service: Annotated[PillarService, Depends(get_pillar_service)],
    user: Annotated[UserShort, Depends(get_current_user)],
) -> PillarModel:
    pillar_create = PillarCreateSchema(**pillar.model_dump(), created_by=user)

    return await pillar_service.create(data=pillar_create)


@router.post(
    '/list',
    operation_id='pillars_list',
    openapi_extra=GatewayEndpointConfig(
        policy='public',
        action=PillarsActions.LIST,
        cache_ttl=0,
    ).model_dump(by_alias=True),
)
async def pillars_list(
    body: Annotated[PillarListBody, Body()],
    opa_query: Annotated[dict, Depends(get_opa_query)],
    pillar_service: Annotated[PillarService, Depends(get_pillar_service)],
) -> PaginatedResponse[PillarWithTgtInfoSchema]:
    query = body.query
    if opa_query:
        query = {'$and': [query, opa_query]}

    return await pillar_service.get_list_paginated(
        query=query, skip=body.skip, limit=body.limit, projection_model=PillarWithTgtInfoSchema, sort=body.sort
    )


@router.put(
    '/{pid}',
    operation_id='pillar_update',
    openapi_extra=GatewayEndpointConfig(
        policy='public',
        action=PillarsActions.UPDATE,
    ).model_dump(by_alias=True),
)
async def pillar_update(
    pid: PyObjectId,
    pillar: PillarUpdateSchema,
    pillar_service: Annotated[PillarService, Depends(get_pillar_service)],
) -> PillarModel:
    return await pillar_service.update(query={'_id': pid}, data=pillar)


@router.delete(
    '/{pid}',
    operation_id='pillar_delete',
    openapi_extra=GatewayEndpointConfig(
        policy='public',
        action=PillarsActions.DELETE,
    ).model_dump(by_alias=True),
)
async def pillar_delete(
    pid: PyObjectId,
    pillar_service: Annotated[PillarService, Depends(get_pillar_service)],
) -> Response:
    await pillar_service.delete(query={'_id': pid})
    return Response(status_code=status.HTTP_204_NO_CONTENT)
