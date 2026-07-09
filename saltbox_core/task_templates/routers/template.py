from typing import Annotated

from fastapi import APIRouter, Body, Depends, status

from saltbox_core.db.schemas_base import TaskiqTaskIdResponse
from saltbox_core.pillars.schemas import PillarTgtType
from saltbox_core.pillars.services.pillar import PillarService, get_pillar_service
from saltbox_core.pillars.utils import PillarSchemaUpdater
from saltbox_core.task_templates.schemas.template import (
    TaskTemplateActions,
    TaskTemplateFromRawCreateSchema,
    TaskTemplateFromRawUpdateSchema,
    TaskTemplateListBody,
    TaskTemplateModel,
    TaskTemplatePublicSchema,
    TaskTemplatePublicWithContentSchema,
)
from saltbox_core.task_templates.services.template import TaskTemplateService, get_task_tpl_service
from saltbox_core.task_templates.tiq_tasks import (
    create_tpl_from_raw_task,
    delete_local_template_task,
    update_tpl_from_raw_task,
)
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.db.schemas_base import PaginatedResponse, UserShort
from saltbox_sdk.discovery_client.schemas import GatewayEndpointConfig
from saltbox_sdk.fastapi_utils.dependencies import get_current_user, get_opa_query

router = APIRouter(prefix='/task-template-sources', tags=['Task Templates / Templates'])


@router.post(
    '/{source_id}/templates/list',
    operation_id='task_template_list',
    openapi_extra=GatewayEndpointConfig(
        policy='core.task_templates.templates.list',
        action=TaskTemplateActions.LIST,
    ).model_dump(by_alias=True),
    response_model=PaginatedResponse[TaskTemplatePublicSchema],
)
async def template_list(
    source_id: PyObjectId,
    body: Annotated[TaskTemplateListBody, Body()],
    opa_query: Annotated[dict, Depends(get_opa_query)],
    service: Annotated[TaskTemplateService, Depends(get_task_tpl_service)],
) -> PaginatedResponse[TaskTemplatePublicSchema]:
    query = {'$and': [{'source_id': source_id}, body.query]}
    if opa_query:
        query = {'$and': [query, opa_query]}
    sources = await service.get_list_paginated(
        query=query,
        skip=body.skip,
        limit=body.limit,
        projection_model=TaskTemplatePublicSchema,
        sort=body.sort,
    )
    return sources


@router.post(
    '/{source_id}/templates',
    operation_id='task_template_create',
    openapi_extra=GatewayEndpointConfig(
        policy='core.task_templates.templates.create',
        action=TaskTemplateActions.CREATE,
    ).model_dump(by_alias=True),
    status_code=status.HTTP_202_ACCEPTED,
    response_model=TaskiqTaskIdResponse,
)
async def template_create(
    source_id: PyObjectId,
    body: Annotated[TaskTemplateFromRawCreateSchema, Body()],
) -> TaskiqTaskIdResponse:
    task = await create_tpl_from_raw_task.kiq(source_id=str(source_id), file_name=body.file_name, content=body.content)
    return TaskiqTaskIdResponse(task_id=task.task_id)


@router.get(
    '/{source_id}/templates/{template_id}/schema-with-defaults',
    operation_id='task_template_schema_with_defaults',
    openapi_extra=GatewayEndpointConfig(
        policy='core.task_templates.templates.read',
        action=TaskTemplateActions.READ,
    ).model_dump(by_alias=True),
    response_model=TaskTemplateModel,
)
async def template_schema_with_defaults(
    source_id: PyObjectId,
    template_id: PyObjectId,
    service: Annotated[TaskTemplateService, Depends(get_task_tpl_service)],
    pillar_service: Annotated[PillarService, Depends(get_pillar_service)],
    user: Annotated[UserShort, Depends(get_current_user)],
) -> TaskTemplateModel:
    task_tpl = await service.get(template_id)
    default_pillars = await pillar_service.get_for_target(
        tgt_type=PillarTgtType.TASK_TPL, tgt_id=template_id, user_sub=user.sub if user else None
    )
    default_setter = PillarSchemaUpdater(schema=task_tpl.json_schema)
    task_tpl.json_schema = default_setter.set_defaults(default_pillars)
    return task_tpl


@router.get(
    '/{source_id}/templates/{template_id}',
    operation_id='task_template_read',
    openapi_extra=GatewayEndpointConfig(
        policy='core.task_templates.templates.read',
        action=TaskTemplateActions.READ,
    ).model_dump(by_alias=True),
    response_model=TaskTemplatePublicWithContentSchema,
)
async def template_read(
    source_id: PyObjectId,
    template_id: PyObjectId,
    service: Annotated[TaskTemplateService, Depends(get_task_tpl_service)],
) -> TaskTemplatePublicWithContentSchema:
    template = await service.get_with_content(template_id)

    return template


@router.put(
    '/{source_id}/templates/{template_id}',
    operation_id='task_template_update',
    openapi_extra=GatewayEndpointConfig(
        policy='public',
        action=TaskTemplateActions.UPDATE,
    ).model_dump(by_alias=True),
    status_code=status.HTTP_202_ACCEPTED,
    response_model=TaskiqTaskIdResponse,
)
async def template_update(
    source_id: PyObjectId,
    template_id: PyObjectId,
    body: Annotated[TaskTemplateFromRawUpdateSchema, Body()],
) -> TaskiqTaskIdResponse:
    task = await update_tpl_from_raw_task.kiq(str(source_id), str(template_id), body.content)
    return TaskiqTaskIdResponse(task_id=task.task_id)


@router.delete(
    '/{source_id}/templates/{template_id}',
    operation_id='task_template_delete',
    openapi_extra=GatewayEndpointConfig(
        policy='public',
        action=TaskTemplateActions.DELETE,
    ).model_dump(by_alias=True),
    status_code=status.HTTP_202_ACCEPTED,
    response_model=TaskiqTaskIdResponse,
)
async def template_delete(
    source_id: PyObjectId,
    template_id: PyObjectId,
) -> TaskiqTaskIdResponse:
    task = await delete_local_template_task.kiq(str(source_id), str(template_id))
    return TaskiqTaskIdResponse(task_id=task.task_id)
