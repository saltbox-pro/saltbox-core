from typing import Annotated

from fastapi import APIRouter, Body, Depends

from saltbox_core.task_templates.schemas.template import (
    TaskTemplateActions,
    TaskTemplateFromRawCreateSchema,
    TaskTemplateListBody,
    TaskTemplatePublicSchema,
    TaskTemplatePublicWithContentSchema,
)
from saltbox_core.task_templates.services.template import TaskTemplateService, get_task_tpl_service
from saltbox_core.task_templates.tiq_tasks import create_tpl_from_raw_task
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.db.schemas_base import PaginatedResponse
from saltbox_sdk.discovery_client.schemas import GatewayEndpointConfig

router = APIRouter(prefix='/task-tpls', tags=['NEW Task Templates'])


@router.post(
    '/list',
    operation_id='new_template_list',
    openapi_extra=GatewayEndpointConfig(
        policy='public',
        action=TaskTemplateActions.LIST,
    ).model_dump(by_alias=True),
    response_model=PaginatedResponse[TaskTemplatePublicSchema],
)
async def template_list(
    body: Annotated[TaskTemplateListBody, Body()],
    service: Annotated[TaskTemplateService, Depends(get_task_tpl_service)],
) -> PaginatedResponse[TaskTemplatePublicSchema]:
    sources = await service.get_list_paginated(
        query=body.query,
        skip=body.skip,
        limit=body.limit,
        projection_model=TaskTemplatePublicSchema,
        sort=body.sort,
    )
    return sources


@router.post(
    '',
    operation_id='new_template_create',
    openapi_extra=GatewayEndpointConfig(
        policy='public',
        action=TaskTemplateActions.CREATE,
    ).model_dump(by_alias=True),
    status_code=202,
)
async def template_create(
    body: Annotated[TaskTemplateFromRawCreateSchema, Body()],
) -> str:
    # oid = await service.create_from_raw(source_id, file_name, content)
    task = await create_tpl_from_raw_task.kiq(
        source_id=str(body.source_id), file_name=body.file_name, content=body.content
    )
    return task.task_id


@router.get(
    '/{template_id}',
    operation_id='new_template_read',
    openapi_extra=GatewayEndpointConfig(
        policy='public',
        action=TaskTemplateActions.READ,
    ).model_dump(by_alias=True),
    response_model=TaskTemplatePublicWithContentSchema,
)
async def template_read(
    template_id: PyObjectId,
    service: Annotated[TaskTemplateService, Depends(get_task_tpl_service)],
) -> TaskTemplatePublicWithContentSchema:
    template = await service.get_with_content(template_id)

    return template
