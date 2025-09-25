from typing import Annotated

from fastapi import APIRouter, Depends, Query

from saltbox_core.settings.schemas.gitlab_schemas import PaginatedGitlabProjects
from saltbox_core.utilities.gitlab_api_client import GitlabApiClient, get_gitlab_api_client
from saltbox_sdk.db.schemas_base import SkipLimitParams
from saltbox_sdk.discovery_client.schemas import GatewayEndpointConfig

router = APIRouter(prefix='/gitlab', tags=['GitLab'])


# TODO (a.baikov): add rate limiting and timeout handling
@router.get(
    '',
    operation_id='project_list',
    openapi_extra=GatewayEndpointConfig(
        policy='public',
        action='list',
    ).model_dump(by_alias=True),
)
async def group_projects_list(
    params: Annotated[SkipLimitParams, Query()],
    service: Annotated[GitlabApiClient, Depends(get_gitlab_api_client)],
) -> PaginatedGitlabProjects:
    return await service.get_configuration_projects_list(skip=params.skip, limit=params.limit)


@router.get(
    '/{project_id}/readme',
    operation_id='project_readme',
    openapi_extra=GatewayEndpointConfig(
        policy='public',
        action='read',
    ).model_dump(by_alias=True),
)
async def project_readme(
    project_id: int,
    service: Annotated[GitlabApiClient, Depends(get_gitlab_api_client)],
) -> dict[str, str | None]:
    file_content = await service.get_readme_by_project_id(project_id=project_id)
    return {'content': file_content}


@router.get(
    '/{project_id}/manifest',
    operation_id='project_manifest',
    openapi_extra=GatewayEndpointConfig(
        policy='public',
        action='read',
    ).model_dump(by_alias=True),
)
async def project_manifest(
    project_id: int,
    service: Annotated[GitlabApiClient, Depends(get_gitlab_api_client)],
) -> dict[str, str | None]:
    file_content = await service.get_manifest_by_project_id(project_id=project_id)
    return {'content': file_content}
