from typing import Annotated

from fastapi import APIRouter, Body, Depends, Response, status

from saltbox_core.config import logger
from saltbox_core.minion_collections.schemas.extra_data_collector import (
    ExtraDataCollectorActions,
    ExtraDataCollectorCreateRequestSchema,
    ExtraDataCollectorCreateSchema,
    ExtraDataCollectorListBody,
    ExtraDataCollectorModel,
    ExtraDataCollectorRunBody,
)
from saltbox_core.minion_collections.services.extra_data_collector import (
    ExtraDataCollectorService,
    get_extra_data_collector_service,
)
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.db.schemas_base import PaginatedResponse, UserShort
from saltbox_sdk.discovery_client.schemas import GatewayEndpointConfig
from saltbox_sdk.fastapi_utils.dependencies import get_current_user

router = APIRouter(prefix='/minions/extra/collectors', tags=['Minions extra data'])


@router.post(
    '/list',
    operation_id='collectors_list',
    # openapi_extra=GatewayEndpointConfig(
    #     policy='core.minions.extra.collectors.list',
    #     action=ExtraDataCollectorActions.LIST,
    # ).model_dump(by_alias=True),
)
async def collectors_list(
    body: Annotated[ExtraDataCollectorListBody, Body()],
    extra_data_collector_service: Annotated[ExtraDataCollectorService, Depends(get_extra_data_collector_service)],
) -> PaginatedResponse[ExtraDataCollectorModel]:
    return await extra_data_collector_service.get_list_paginated(
        query=body.query,
        skip=body.skip,
        limit=body.limit,
        projection_model=ExtraDataCollectorModel,
        sort=body.sort,
    )


@router.post(
    '/create',
    operation_id='collector_create',
    # openapi_extra=GatewayEndpointConfig(
    #     policy='core.minions.extra.collectors.create',
    #     action=ExtraDataCollectorActions.CREATE,
    # ).model_dump(by_alias=True),
)
async def collector_create(
    item: ExtraDataCollectorCreateRequestSchema,
    user: Annotated[UserShort, Depends(get_current_user)],
    extra_data_collector_service: Annotated[ExtraDataCollectorService, Depends(get_extra_data_collector_service)],
) -> ExtraDataCollectorModel:
    obj_id = await extra_data_collector_service.create(
        data=ExtraDataCollectorCreateSchema.model_validate(
            {
                'user': user.model_dump(),
                **item.model_dump(by_alias=True),
            }
        )
    )
    return await extra_data_collector_service.get(query=obj_id)


@router.get(
    '/{collector_id}',
    operation_id='collector_get',
    # openapi_extra=GatewayEndpointConfig(
    #     policy='core.minions.extra.collectors.read',
    #     action=ExtraDataCollectorActions.READ,
    # ).model_dump(by_alias=True),
)
async def collector_retrieve(
    collector_id: PyObjectId,
    extra_data_collector_service: Annotated[ExtraDataCollectorService, Depends(get_extra_data_collector_service)],
) -> ExtraDataCollectorModel:
    return await extra_data_collector_service.get(collector_id)


@router.delete(
    '/{collector_id}/delete',
    operation_id='collector_delete',
    # openapi_extra=GatewayEndpointConfig(
    #     policy='core.minions.extra.collectors.delete',
    #     action=ExtraDataCollectorActions.DELETE,
    # ).model_dump(by_alias=True),
    status_code=status.HTTP_204_NO_CONTENT,
)
async def collector_delete(
    collector_id: PyObjectId,
    extra_data_collector_service: Annotated[ExtraDataCollectorService, Depends(get_extra_data_collector_service)],
) -> Response:
    await extra_data_collector_service.delete({'id': collector_id, 'is_preinstalled': False})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    '/{collector_id}/run',
    operation_id='collector_run',
    # openapi_extra=GatewayEndpointConfig(
    #     policy='core.minions.extra.collectors.run',
    #     action=ExtraDataCollectorActions.DELETE,
    # ).model_dump(by_alias=True),
)
async def collector_run(
    collector_id: PyObjectId,
    body: ExtraDataCollectorRunBody,
    extra_data_collector_service: Annotated[ExtraDataCollectorService, Depends(get_extra_data_collector_service)],
) -> Response:
    await extra_data_collector_service.run(collector_id=collector_id, launch_data=body.launch_data)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
