from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from salt_box_core.config import logger

# from salt_box_core.db.exceptions import DuplicateKeyError, ObjectNotFoundError
from salt_box_core.db.exceptions import ObjectNotFoundError
from salt_box_core.db.mongo.schemas_base import PaginatedResponse, PyObjectId, User
from salt_box_core.dependencies import get_current_user_from_jwt
from salt_box_core.settings.schemas.sls_repos_schemas import SettingsSlsRepoShortSchema
from salt_box_core.settings.services.sls_repo_service import SettingsSlsRepoService, get_sls_repo_service
from salt_box_core.tasks.schemas.task_template_schemas import (
    TaskTemplateListQueryParams,
    TaskTemplateModel,
    TaskTemplateShortSchema,
)
from salt_box_core.tasks.services.tasks_templates import TaskTemplateService, get_task_template_service

router = APIRouter(prefix='/tasks/template', tags=['Task Templates'])


@router.get('')
async def task_template_list(
    params: Annotated[TaskTemplateListQueryParams, Query()],
    service: Annotated[TaskTemplateService, Depends(get_task_template_service)],
    repo_settings_service: Annotated[SettingsSlsRepoService, Depends(get_sls_repo_service)],
    user: Annotated[User, Depends(get_current_user_from_jwt)],  # type: ignore[unused-ignore]
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

    try:
        return await service.get_list_paginated(
            query=query,
            skip=params.skip,
            limit=params.limit,
            projection_model=TaskTemplateShortSchema,
        )
    except Exception as e:
        msg = f'{e!s}'
        logger.error(msg)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=msg) from e


@router.get('/{tpl_id}')
async def task_template_retrieve(
    tpl_id: PyObjectId,
    service: Annotated[TaskTemplateService, Depends(get_task_template_service)],
    user: Annotated[User, Depends(get_current_user_from_jwt)],  # type: ignore[unused-ignore]
) -> TaskTemplateModel:
    try:
        return await service.get(tpl_id)
    except ObjectNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except Exception as e:
        msg = f'{e!s}'
        logger.error(msg)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=msg) from e
