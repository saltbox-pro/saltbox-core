from typing import Annotated

from fastapi import APIRouter, Depends, Query

from saltbox_core.settings.schemas.sls_repos_schemas import SettingsSlsRepoShortSchema
from saltbox_core.settings.services.sls_repo_service import SettingsSlsRepoService, get_sls_repo_service
from saltbox_core.tasks.schemas.task_template_schemas import (
    TaskTemplateListQueryParams,
    TaskTemplateModel,
    TaskTemplateShortSchema,
)
from saltbox_core.tasks.services.tasks_templates import TaskTemplateService, get_task_template_service
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.db.schemas_base import PaginatedResponse

router = APIRouter(prefix='/tasks/template', tags=['Task Templates'])


@router.get('')
async def task_template_list(
    params: Annotated[TaskTemplateListQueryParams, Query()],
    service: Annotated[TaskTemplateService, Depends(get_task_template_service)],
    repo_settings_service: Annotated[SettingsSlsRepoService, Depends(get_sls_repo_service)],
) -> PaginatedResponse[TaskTemplateShortSchema]:
    active_repos = await repo_settings_service.get_list(
        query={'is_active': True}, skip=0, limit=0, projection_model=SettingsSlsRepoShortSchema
    )
    active_repo_ids = [repo.id for repo in active_repos]
    selected_repos_query = {'repo_id': {'$in': params.repo_ids}} if params.repo_ids else {}

    query = {
        '$and': [
            {'repo_id': {'$in': active_repo_ids}},
            selected_repos_query,
        ]
    }

    return await service.get_list_paginated(
        query=query,
        skip=params.skip,
        limit=params.limit,
        projection_model=TaskTemplateShortSchema,
    )


@router.get('/{tpl_id}')
async def task_template_retrieve(
    tpl_id: PyObjectId,
    service: Annotated[TaskTemplateService, Depends(get_task_template_service)],
) -> TaskTemplateModel:
    return await service.get(tpl_id)
