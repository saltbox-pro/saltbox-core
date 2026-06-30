from typing import Annotated

from fastapi import APIRouter, Body, Depends

from saltbox_core.task_templates.schemas.template import (
    TaskTemplateActions,
    TaskTemplateSchemaResponse,
    TaskTemplateSchemasListRequest,
)
from saltbox_core.task_templates.services.template import TaskTemplateService, get_task_tpl_service
from saltbox_sdk.discovery_client.schemas import GatewayEndpointConfig

router = APIRouter(prefix='/task-template-schemas', tags=['Task Templates / Schemas'])


@router.get(
    '/{tpl_name}',
    operation_id='task_template_schema_by_name',
    openapi_extra=GatewayEndpointConfig(
        policy='public',
        action=TaskTemplateActions.READ,
    ).model_dump(by_alias=True),
)
async def task_template_schema_by_name(
    tpl_name: str,
    service: Annotated[TaskTemplateService, Depends(get_task_tpl_service)],
) -> TaskTemplateSchemaResponse:
    return await service.get(query={'name': tpl_name}, projection_model=TaskTemplateSchemaResponse)


@router.post(
    '/list',
    operation_id='task_template_schemas_list',
    openapi_extra=GatewayEndpointConfig(
        policy='public',
        action=TaskTemplateActions.READ,
    ).model_dump(by_alias=True),
)
async def task_template_schemas_list(
    body: Annotated[TaskTemplateSchemasListRequest, Body()],
    service: Annotated[TaskTemplateService, Depends(get_task_tpl_service)],
) -> dict[str, dict[str, dict]]:
    return await service.get_schemas_by_names(body.names)
