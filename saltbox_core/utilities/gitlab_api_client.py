import httpx

from saltbox_core.settings.exceptions import MissingGroupIdException
from saltbox_core.settings.schemas.gitlab_schemas import GitlabProjectSchema, PaginatedGitlabProjects
from saltbox_core.settings.tasks import SETTINGS
from saltbox_core.utilities.httpx_client import HttpxClientSingletoneFactory


class GitlabApiClient:
    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        httpx_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._httpx_client = httpx_client or httpx.AsyncClient()
        self._token = token
        self._base_url = base_url

    async def get_configuration_projects_list(self, skip: int = 0, limit: int = 20) -> PaginatedGitlabProjects:
        per_page = limit if limit > 0 else 20
        page = (skip // per_page) + 1 if skip >= 0 else 0
        if not SETTINGS.gitlab_group_id:
            raise MissingGroupIdException()

        url = f'{self._base_url}/api/v4/groups/{SETTINGS.gitlab_group_id}/projects'
        headers = {}
        if self._token:
            headers['Authorization'] = f'Bearer {self._token}'

        query_params = {
            'archived': 'false',
            'per_page': str(per_page),
            'page': str(page),
            'order_by': 'id',
            'sort': 'asc',
        }  # per_page=20 is GitLab default
        response = await self._httpx_client.get(url, headers=headers, params=query_params)
        response.raise_for_status()
        projects_data = response.json()

        total = response.headers.get('x-total')

        return PaginatedGitlabProjects(
            total=total,
            items=[
                GitlabProjectSchema(**item)
                for item in projects_data
                if item.get('marked_for_deletion_on') is None and item.get('marked_for_deletion_at') is None
            ],
        )

    async def get_readme_by_project_id(self, project_id: int) -> str | None:
        return await self._get_file_by_project_id(project_id, file_name='README.md')

    async def get_manifest_by_project_id(self, project_id: int) -> str | None:
        return await self._get_file_by_project_id(project_id, file_name='manifest.yaml')

    async def _get_file_by_project_id(self, project_id: int, file_name: str) -> str | None:
        url = f'{self._base_url}/api/v4/projects/{project_id}/repository/files/{file_name}/raw'
        headers = {}
        if self._token:
            headers['Authorization'] = f'Bearer {self._token}'
        response = await self._httpx_client.get(url, headers=headers)
        if response.status_code == 200:
            return response.text
        elif response.status_code == 404:
            return None
        else:
            response.raise_for_status()
            return None


def get_gitlab_api_client() -> GitlabApiClient:
    """Get an instance of the GitLab API client."""
    httpx_client = HttpxClientSingletoneFactory.get_instance()
    return GitlabApiClient(token=SETTINGS.gitlab_token, base_url=SETTINGS.gitlab_base_url, httpx_client=httpx_client)
