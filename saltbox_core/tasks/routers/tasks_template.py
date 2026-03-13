from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends

from saltbox_core.settings.schemas.sls_repos_schemas import SettingsSlsRepoShortSchema
from saltbox_core.settings.services.sls_repo_service import SettingsSlsRepoService, get_sls_repo_service
from saltbox_core.tasks.schemas.tasks_template import (
    TaskTemplateListBody,
    TaskTemplateModel,
    TaskTemplatesActions,
    TaskTemplateSchemaResponse,
    TaskTemplateShortSchema,
)
from saltbox_core.tasks.services.tasks_template import TaskTemplateService, get_task_template_service
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.db.schemas_base import PaginatedResponse
from saltbox_sdk.discovery_client.schemas import GatewayEndpointConfig
from saltbox_sdk.fastapi_utils.dependencies import get_opa_query

router = APIRouter(prefix='/tasks/template', tags=['Task Templates'])


@router.post(
    '',
    operation_id='task_templates_list',
    openapi_extra=GatewayEndpointConfig(
        policy='core.tasks.templates.list',
        action=TaskTemplatesActions.LIST,
    ).model_dump(by_alias=True),
)
async def task_template_list(
    body: Annotated[TaskTemplateListBody, Body()],
    opa_query: Annotated[dict, Depends(get_opa_query)],
    service: Annotated[TaskTemplateService, Depends(get_task_template_service)],
    repo_settings_service: Annotated[SettingsSlsRepoService, Depends(get_sls_repo_service)],
) -> PaginatedResponse[TaskTemplateShortSchema]:
    active_repos = await repo_settings_service.get_list(
        query={'is_active': True}, skip=0, limit=0, projection_model=SettingsSlsRepoShortSchema
    )

    query_filters: list[dict[str, Any]] = [
        {'repo_id': {'$in': [repo.id for repo in active_repos]}},
    ]

    if body.repo_ids:
        query_filters.append({'repo_id': {'$in': body.repo_ids}})
    if body.query:
        query_filters.append(body.query)
    if opa_query:
        query_filters.append(opa_query)

    if len(query_filters) > 1:
        query: dict[str, Any] = {'$and': query_filters}
    else:
        query = query_filters[0]

    return await service.get_list_paginated(
        query=query,
        skip=body.skip,
        limit=body.limit,
        projection_model=TaskTemplateShortSchema,
        sort=body.sort,
    )


@router.get(
    '/schema-by-name/{tpl_name}',
    operation_id='task_template_schema_by_name',
    openapi_extra=GatewayEndpointConfig(
        policy='core.tasks.templates.read',
        action=TaskTemplatesActions.READ,
    ).model_dump(by_alias=True),
)
async def task_template_schema_by_name(
    tpl_name: str,
    service: Annotated[TaskTemplateService, Depends(get_task_template_service)],
) -> TaskTemplateSchemaResponse:
    return await service.get(query={'name': tpl_name}, projection_model=TaskTemplateSchemaResponse)


@router.get(
    '/{tpl_id}',
    operation_id='task_template_retrieve',
    openapi_extra=GatewayEndpointConfig(
        policy='core.tasks.templates.read',
        action=TaskTemplatesActions.READ,
    ).model_dump(by_alias=True),
)
async def task_template_retrieve(
    tpl_id: PyObjectId,
    service: Annotated[TaskTemplateService, Depends(get_task_template_service)],
) -> TaskTemplateModel:
    return await service.get(tpl_id)
