from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from salt_box_core.config import logger

# from salt_box_core.db.exceptions import DuplicateKeyError, ObjectNotFoundError
from salt_box_core.db.exceptions import ObjectNotFoundError
from salt_box_core.db.mongo.schemas_base import PaginatedResponse, PyObjectId, SkipLimitParams
from salt_box_core.sls_repos.schemas.settings_schemas import SettingsSlsRepoShortSchema
from salt_box_core.sls_repos.schemas.tpl_schemas import SlsTplModel, SlsTplShortSchema
from salt_box_core.sls_repos.services.sls_repo_service import SettingsSlsRepoService, get_sls_repo_service
from salt_box_core.sls_repos.services.sls_tpl_service import SlsTplService, get_sls_tpl_service

router = APIRouter(prefix='/sls-templates', tags=['SLS Templates'])


@router.get('')
async def sls_template_list(
    params: Annotated[SkipLimitParams, Query()],
    service: Annotated[SlsTplService, Depends(get_sls_tpl_service)],
    repo_settings_service: Annotated[SettingsSlsRepoService, Depends(get_sls_repo_service)],
) -> PaginatedResponse[SlsTplShortSchema]:
    active_repos = await repo_settings_service.get_list(
        query={'is_active': True}, skip=0, limit=0, projection_model=SettingsSlsRepoShortSchema
    )
    active_repo_ids = [repo.id for repo in active_repos]
    try:
        return await service.get_list_paginated(
            query={'repo_id': {'$in': active_repo_ids}},
            skip=params.skip,
            limit=params.limit,
            projection_model=SlsTplShortSchema,
        )
    except Exception as e:
        msg = f'{e!s}'
        logger.error(msg)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=msg) from e


@router.get('/{tpl_id}')
async def sls_template_get(
    tpl_id: PyObjectId,
    service: Annotated[SlsTplService, Depends(get_sls_tpl_service)],
) -> SlsTplModel:
    try:
        return await service.get(tpl_id)
    except ObjectNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except Exception as e:
        msg = f'{e!s}'
        logger.error(msg)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=msg) from e
