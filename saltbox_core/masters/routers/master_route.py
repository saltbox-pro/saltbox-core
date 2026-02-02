from typing import Annotated

from fastapi import APIRouter, Body, Depends

from saltbox_core.event_bus.redis.masters_bus import notify_master_on_repos_update
from saltbox_core.masters.schemas.master_schemas import MasterListBody, MasterModel, MastersActions, MasterViewSchema
from saltbox_core.masters.services.master_service import MasterService, get_master_service
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.db.schemas_base import PaginatedResponse
from saltbox_sdk.discovery_client.schemas import GatewayEndpointConfig

router = APIRouter(prefix='/masters', tags=['Masters'])


@router.post(
    '',
    operation_id='masters_list',
    openapi_extra=GatewayEndpointConfig(
        policy='core.masters.list',
        action=MastersActions.LIST,
    ).model_dump(by_alias=True),
)
async def masters_list(
    body: Annotated[MasterListBody, Body()],
    master_service: Annotated[MasterService, Depends(get_master_service)],
) -> PaginatedResponse[MasterViewSchema]:
    query = body.query

    if body.status:
        query = {'$and': [query, {'status': body.status}]}

    master_list: PaginatedResponse[MasterViewSchema] = await master_service.get_list_paginated(
        query=query,
        limit=body.limit,
        skip=body.skip,
        projection_model=MasterViewSchema,
        sort=body.sort,
    )

    return master_list


@router.get(
    '/{master_id}',
    operation_id='master_get',
    openapi_extra=GatewayEndpointConfig(
        policy='core.masters.base',
        action=MastersActions.READ,
    ).model_dump(by_alias=True),
)
async def master_get(
    master_id: str,
    master_service: Annotated[MasterService, Depends(get_master_service)],
) -> MasterViewSchema:
    master: MasterModel = await master_service.get_by_master_id(master_id)
    return MasterViewSchema.model_validate({'_id': master.id, **master.model_dump(by_alias=True)})


@router.post(
    '/{mid}/accept',
    operation_id='task_accept',
    openapi_extra=GatewayEndpointConfig(
        policy='core.masters.base',
        action=MastersActions.ACCEPT,
    ).model_dump(by_alias=True),
)
async def master_accept(
    mid: PyObjectId,
    master_service: Annotated[MasterService, Depends(get_master_service)],
) -> MasterViewSchema:
    master: MasterModel = await master_service.accept(mid)

    await notify_master_on_repos_update(master)
    return MasterViewSchema.model_validate({'_id': master.id, **master.model_dump(by_alias=True)})


@router.post(
    '/{mid}/reject',
    operation_id='task_reject',
    openapi_extra=GatewayEndpointConfig(
        policy='core.masters.base',
        action=MastersActions.REJECT,
    ).model_dump(by_alias=True),
)
async def master_reject(
    mid: PyObjectId,
    master_service: Annotated[MasterService, Depends(get_master_service)],
) -> MasterViewSchema:
    master: MasterModel = await master_service.reject(mid)
    return MasterViewSchema.model_validate({'_id': master.id, **master.model_dump(by_alias=True)})
