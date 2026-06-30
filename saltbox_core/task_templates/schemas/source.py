from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, SecretStr, field_serializer, field_validator

from saltbox_core.task_templates.schemas.sshfs_file import SshfsFilePublicSchema
from saltbox_core.task_templates.schemas.template import TaskTemplatePublicSchema
from saltbox_sdk.db.mongo.schemas_base import IDMixin, QueryParams, SortParams
from saltbox_sdk.db.schemas_base import CreatedModifiedMixin, SkipLimitParams
from saltbox_sdk.utilities.helpers import Iso8601ZDatetime


class SourceType(StrEnum):
    GIT_REPO = 'git_repo'
    ARCHIVE_BUNDLE = 'archive_bundle'
    LOCAL_BUNDLE = 'local_bundle'


class SourceState(StrEnum):
    """State of the template source.
    PENDING - just created, not yet discovered)
    DISCOVERED - pulled with depth=1, templates parsed and saved, manifest parsed, files instances created
    PLUGGED - templates rsync to serve_dir, files downloaded to SSHFS, ready to be served to masters
    ACTIVE - templates and files served to masters
    BROKEN - last operation failed, needs attention
    """

    PENDING = 'pending'
    DISCOVERED = 'discovered'
    PLUGGED = 'plugged'
    ACTIVE = 'active'
    BROKEN = 'broken'


class SourceOperation(StrEnum):
    """Operation in progress for the template source. None means no operation in progress."""

    DISCOVER = 'discover'
    PREPARE_TEMPLATES = 'prepare_templates'
    UPDATE_TEMPLATE_CONTENT = 'update_template_content'
    ADD_TEMPLATE_FROM_RAW = 'add_template_from_raw'
    DELETE_LOCAL_TEMPLATE = 'delete_local_template'
    PREPARE_FILES = 'prepare_files'
    ADD_USER_FILE = 'add_user_file'
    SYNC = 'sync'
    REMOVE = 'remove'
    UNPLUG = 'unplug'


class TemplateSourceImportFromGitSchema(BaseModel):
    name: str = Field(min_length=1, max_length=100, title='Display name')
    description: str | None = Field(default='', max_length=500, title='Description')
    namespace: str = Field(
        default='',
        max_length=64,
        pattern=r'^[a-z0-9_]*$',
        title='Namespace',
        description='Prefix for template names and serve_dir subdirectory. Empty means no prefix.',
    )
    repo_url: HttpUrl = Field(title='Git repository URL')
    repo_user: str | None = Field(default=None, title='Git user (basic auth)')
    repo_pass: str | None = Field(default=None, title='Git password (basic auth)')
    branch: str | None = Field(default=None, max_length=100, title='Git branch')


class TemplateSourceCreateLocalSchema(BaseModel):
    name: str = Field(min_length=1, max_length=100, title='Display name')
    description: str | None = Field(default='', max_length=500, title='Description')
    namespace: str = Field(
        default='',
        max_length=64,
        pattern=r'^[a-z0-9_]*$',
        title='Namespace',
        description='Prefix for template names and serve_dir subdirectory. Empty means no prefix.',
    )

    @field_validator('name')
    @classmethod
    def name_must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            msg = 'name must not be blank'
            raise ValueError(msg)
        return v


class TemplateSourceCreateSchema(BaseModel):
    source_type: SourceType = Field(title='Source type')
    name: str = Field(min_length=1, max_length=100, title='Display name')
    description: str | None = Field(default='', max_length=500, title='Description')
    # Ненулевой namespace даёт: serve_dir/<namespace>/... и name (mods) = "<namespace>.<dot_path>"
    namespace: str = Field(
        default='',
        max_length=64,
        pattern=r'^[a-z0-9_]*$',
        title='Namespace',
        description='Prefix for template names and serve_dir subdirectory. Empty means no prefix.',
    )
    repo_url: HttpUrl | None = Field(default=None, title='Git repository URL')
    repo_user: str | None = Field(default=None, title='Git user (basic auth)')
    repo_pass: str | None = Field(default=None, title='Git password (basic auth)')
    branch: str | None = Field(default=None, max_length=100, title='Git branch')

    @field_serializer('repo_url')
    def serialize_url(self, url: HttpUrl | None) -> str | None:
        return str(url) if url else None


class TemplateSourceUpdateSchema(BaseModel):
    name: str | None = None
    description: str | None = None


class TemplateSourceModel(CreatedModifiedMixin, IDMixin):
    name: str = Field(min_length=1, max_length=100, title='Display name')
    description: str | None = Field(default='', max_length=500, title='Description')
    # is_active: bool = Field(default=False, title='Is active (publish to serve_dir)')
    namespace: str = Field(
        default='',
        max_length=64,
        pattern=r'^[a-z0-9_]*$',
        title='Namespace',
        description='Prefix for template names and serve_dir subdirectory. Empty means no prefix.',
    )
    source_type: SourceType = Field(title='Source type')
    repo_url: HttpUrl | None = Field(default=None, title='Git repository URL')
    repo_user: str | None = Field(default=None, title='Git user (basic auth)')
    repo_pass: SecretStr | None = Field(default=None, title='Git password (basic auth)')
    branch: str | None = Field(default=None, max_length=100, title='Git branch')
    local_path: str = Field(default='', max_length=32, pattern=r'^[a-z0-9_\-]*$', title='Local storage path')
    root: str = Field(default='', title='Path in repository to serve for masters')
    state: SourceState = Field(title='State of the template source')
    current_operation: SourceOperation | None = Field(default=None, title='Current operation in progress')
    current_task_id: str | None = Field(default=None, title='Current task ID for the operation in progress')
    last_error: str | None = Field(default=None, title='Last error message if state is BROKEN')
    synced_at: Iso8601ZDatetime | None = Field(default=None, title='Last sync time')

    @field_serializer('repo_url')
    def serialize_url(self, url: HttpUrl | None) -> str | None:
        return str(url) if url else None


class TemplateSourcePublicSchema(CreatedModifiedMixin, IDMixin):
    name: str
    description: str | None = Field(default='', max_length=1000)
    namespace: str = Field(default='')
    source_type: SourceType
    repo_url: HttpUrl | None = None
    repo_user: str | None = None
    repo_pass: SecretStr | None = None
    branch: str | None = None
    local_path: str
    state: SourceState
    current_operation: SourceOperation | None
    current_task_id: str | None = Field(default=None)
    last_error: str | None
    synced_at: Iso8601ZDatetime | None

    model_config = ConfigDict(from_attributes=True)

    @field_serializer('repo_url')
    def serialize_url(self, url: HttpUrl | None) -> str | None:
        return str(url) if url else None


class TemplateSourceListBody(SkipLimitParams, QueryParams, SortParams):
    model_config = ConfigDict(extra='ignore')


class SourceListWithExtrasSchema(TemplateSourcePublicSchema):
    templates: list[TaskTemplatePublicSchema] = Field(default_factory=list)
    files: list[SshfsFilePublicSchema] = Field(default_factory=list)


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


class TemplateSourceActions(StrEnum):
    LIST = 'list'
    READ = 'read'
    CREATE = 'create'
    UPDATE = 'update'
    DELETE = 'delete'
    PLUG = 'plug'
    UNPLUG = 'unplug'
    SYNC = 'sync'
    DISCOVER = 'discover'
    DELETE_USER_FILE = 'delete_user_file'
    ADD_USER_FILE = 'add_user_file'
    FILES_LIST = 'files_list'
    CHECK_EXTERNAL_LIST = 'check_external_list'
