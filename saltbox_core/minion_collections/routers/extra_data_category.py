from typing import Annotated

from fastapi import APIRouter, Body, Depends, Response, status

from saltbox_core.minion_collections.schemas.extra_data_category import (
    ExtraDataCategoryActions,
    ExtraDataCategoryCreateRequestSchema,
    ExtraDataCategoryCreateSchema,
    ExtraDataCategoryListBody,
    ExtraDataCategoryModel,
)
from saltbox_core.minion_collections.services.extra_data_category import (
    ExtraDataCategoryService,
    get_extra_data_category_service,
)
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.db.schemas_base import PaginatedResponse, UserShort
from saltbox_sdk.discovery_client.schemas import GatewayEndpointConfig
from saltbox_sdk.fastapi_utils.dependencies import get_current_user

router = APIRouter(prefix='/minions/extra/categories', tags=['Minions extra data'])


@router.post(
    '/list',
    operation_id='categories_list',
    # openapi_extra=GatewayEndpointConfig(
    #     policy='core.minions.extra.categories.list',
    #     action=ExtraDataCollectorActions.LIST,
    # ).model_dump(by_alias=True),
)
async def categories_list(
    body: Annotated[ExtraDataCategoryListBody, Body()],
    extra_data_category_service: Annotated[ExtraDataCategoryService, Depends(get_extra_data_category_service)],
) -> PaginatedResponse[ExtraDataCategoryModel]:
    return await extra_data_category_service.get_list_paginated(
        query=body.query,
        skip=body.skip,
        limit=body.limit,
        projection_model=ExtraDataCategoryModel,
        sort=body.sort,
    )


@router.post(
    '/create',
    operation_id='category_create',
    # openapi_extra=GatewayEndpointConfig(
    #     policy='core.minions.extra.categories.create',
    #     action=ExtraDataCollectorActions.CREATE,
    # ).model_dump(by_alias=True),
)
async def category_create(
    item: ExtraDataCategoryCreateRequestSchema,
    user: Annotated[UserShort, Depends(get_current_user)],
    extra_data_category_service: Annotated[ExtraDataCategoryService, Depends(get_extra_data_category_service)],
) -> ExtraDataCategoryModel:
    obj_id = await extra_data_category_service.create(
        data=ExtraDataCategoryCreateSchema.model_validate(
            {
                'user': user.model_dump(),
                **item.model_dump(by_alias=True),
            }
        )
    )
    return await extra_data_category_service.get(query=obj_id)


@router.get(
    '/{category_id}',
    operation_id='category_get',
    # openapi_extra=GatewayEndpointConfig(
    #     policy='core.minions.extra.categories.read',
    #     action=ExtraDataCollectorActions.READ,
    # ).model_dump(by_alias=True),
)
async def category_retrieve(
    category_id: PyObjectId,
    extra_data_category_service: Annotated[ExtraDataCategoryService, Depends(get_extra_data_category_service)],
) -> ExtraDataCategoryModel:
    return await extra_data_category_service.get(category_id)


@router.delete(
    '/{category_id}/delete',
    operation_id='category_delete',
    # openapi_extra=GatewayEndpointConfig(
    #     policy='core.minions.extra.categories.delete',
    #     action=ExtraDataCollectorActions.DELETE,
    # ).model_dump(by_alias=True),
    status_code=status.HTTP_204_NO_CONTENT,
)
async def category_delete(
    category_id: PyObjectId,
    extra_data_category_service: Annotated[ExtraDataCategoryService, Depends(get_extra_data_category_service)],
) -> Response:
    await extra_data_category_service.delete({'id': category_id, 'is_preinstalled': False})
    return Response(status_code=status.HTTP_204_NO_CONTENT)
