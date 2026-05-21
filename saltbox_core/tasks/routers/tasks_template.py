from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Response, status

from saltbox_core.pillars.schemas import PillarTgtType
from saltbox_core.pillars.services.pillar import PillarService, get_pillar_service
from saltbox_core.pillars.utils import PillarSchemaUpdater
from saltbox_core.settings.services.sls_repo_service import SettingsSlsRepoService, get_sls_repo_service
from saltbox_core.tasks.schemas.tasks_template import (
    TaskTemplateCreateSchema,
    TaskTemplateExcludeSlsSchema,
    TaskTemplateListBody,
    TaskTemplateModel,
    TaskTemplatesActions,
    TaskTemplateSchemaResponse,
    TaskTemplateSchemasListRequest,
    TaskTemplateShortSchema,
    TaskTemplateUpdateSchema,
)
from saltbox_core.tasks.services.tasks_template import TaskTemplateService, get_task_template_service
from saltbox_sdk.db.mongo.schemas_base import EmptyModel, PyObjectId
from saltbox_sdk.db.schemas_base import PaginatedResponse, UserShort
from saltbox_sdk.discovery_client.schemas import GatewayEndpointConfig
from saltbox_sdk.fastapi_utils.dependencies import get_current_user, get_opa_query

router = APIRouter(prefix='/tasks/template', tags=['Task Templates'])


@router.post(
    '/list',
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
        query={'is_active': True}, skip=0, limit=0, projection_model=EmptyModel
    )

    query_filters: list[dict[str, Any]] = [
        {
            '$or': [
                {'repo_id': {'$in': [repo.id for repo in active_repos]}},
                {'repo_id': None},
            ]
        }
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


@router.post(
    '/schemas-list',
    operation_id='task_template_schemas_list',
    openapi_extra=GatewayEndpointConfig(
        policy='core.tasks.templates.read',
        action=TaskTemplatesActions.READ,
    ).model_dump(by_alias=True),
)
async def task_template_schemas_list(
    body: Annotated[TaskTemplateSchemasListRequest, Body()],
    service: Annotated[TaskTemplateService, Depends(get_task_template_service)],
) -> dict[str, dict[str, dict]]:
    return await service.get_schemas_by_names(body.names)


@router.post(
    '',
    operation_id='task_template_create',
    openapi_extra=GatewayEndpointConfig(
        policy='core.tasks.templates.create',
        action=TaskTemplatesActions.CREATE,
    ).model_dump(by_alias=True),
)
async def task_template_create(
    item: TaskTemplateCreateSchema,
    service: Annotated[TaskTemplateService, Depends(get_task_template_service)],
) -> TaskTemplateModel:
    obj_id = await service.create(item)
    return await service.get(query=obj_id)


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


@router.get(
    '/{tpl_id}/with-defaults',
    operation_id='task_template_retrieve_with_defaults',
    openapi_extra=GatewayEndpointConfig(
        policy='core.tasks.templates.read',
        action=TaskTemplatesActions.READ,
    ).model_dump(by_alias=True),
)
async def task_template_retrieve_with_defaults(
    tpl_id: PyObjectId,
    service: Annotated[TaskTemplateService, Depends(get_task_template_service)],
    pillar_service: Annotated[PillarService, Depends(get_pillar_service)],
    user: Annotated[UserShort, Depends(get_current_user)],
) -> TaskTemplateExcludeSlsSchema:
    task_tpl = await service.get(tpl_id, projection_model=TaskTemplateExcludeSlsSchema)
    default_pillars = await pillar_service.get_for_target(
        tgt_type=PillarTgtType.TASK_TPL, tgt_id=tpl_id, user_sub=user.sub if user else None
    )
    default_setter = PillarSchemaUpdater(schema=task_tpl.json_schema)
    task_tpl.json_schema = default_setter.set_defaults(default_pillars)
    return task_tpl


@router.delete(
    '/{tpl_id}',
    operation_id='task_template_delete',
    openapi_extra=GatewayEndpointConfig(
        policy='core.tasks.templates.delete',
        action=TaskTemplatesActions.DELETE,
    ).model_dump(by_alias=True),
)
async def task_template_delete(
    tpl_id: PyObjectId,
    service: Annotated[TaskTemplateService, Depends(get_task_template_service)],
) -> Response:
    await service.delete(query={'_id': tpl_id, 'repo_id': None})

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    '/{tpl_id}',
    operation_id='task_template_update',
    openapi_extra=GatewayEndpointConfig(
        policy='core.tasks.templates.update',
        action=TaskTemplatesActions.UPDATE,
    ).model_dump(by_alias=True),
)
async def task_template_update(
    tpl_id: PyObjectId,
    item: TaskTemplateUpdateSchema,
    service: Annotated[TaskTemplateService, Depends(get_task_template_service)],
) -> TaskTemplateModel:
    obj_id = await service.update(query={'_id': tpl_id, 'repo_id': None}, data=item)
    return await service.get(query=obj_id)
