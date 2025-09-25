from pydantic import BaseModel


class GitlabProjectSchema(BaseModel):
    id: int
    name: str
    description: str | None = None
    name_with_namespace: str
    path: str
    path_with_namespace: str
    created_at: str
    default_branch: str
    ssh_url_to_repo: str
    http_url_to_repo: str
    web_url: str
    readme_url: str | None = None
    star_count: int
    forks_count: int
    tag_list: list[str]
    topics: list[str]
    visibility: str
    last_activity_at: str
    updated_at: str
    empty_repo: bool
    archived: bool
    marked_for_deletion_on: str | None = None
    marked_for_deletion_at: str | None = None


class PaginatedGitlabProjects(BaseModel):
    total: int
    items: list[GitlabProjectSchema]
