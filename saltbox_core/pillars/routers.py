from typing import Annotated

from fastapi import APIRouter, Body, Depends

# from saltbox_core.config import logger
from saltbox_core.pillars.schemas import (
    PillarCreateSchema,
    PillarListBody,
    PillarModel,
    PillarsActions,
)
from saltbox_core.pillars.services import PillarService, get_pillar_service
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
    pillar: PillarCreateSchema,
    pillar_service: Annotated[PillarService, Depends(get_pillar_service)],
    user: Annotated[UserShort, Depends(get_current_user)],
) -> PillarModel:
    pillar = pillar.model_copy(
        update={
            'created_by': user,
        }
    )

    return await pillar_service.create(data=pillar)


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
) -> PaginatedResponse[PillarModel]:
    query = body.query
    if opa_query:
        query = {'$and': [query, opa_query]}

    return await pillar_service.get_list_paginated(
        query=query, skip=body.skip, limit=body.limit, projection_model=PillarModel, sort=body.sort
    )
