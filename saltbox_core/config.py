import logging.config
import os
from datetime import timedelta
from functools import cached_property
from pathlib import Path
from typing import Annotated

from pydantic import AfterValidator, BaseModel, DirectoryPath, Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

from saltbox_core.utilities.filesystem import TreePermissions, remove_older_than

APP_NAME = 'Salt.Box Core'
APP_DESC = 'Salt.Box Core API'
CACHE_LIFETIME = timedelta(days=1)
ENV_FILE = Path(os.environ.get('SALTBOX_ENV_FILE', '.env'))

# SLS repo Manifest file possible names
MANIFEST_FILE_ALLOWED_NAMES = ('manifest.yaml', 'manifest.yml')


def validate_path_is_absolute(value: Path) -> Path:
    """value must not be a relative Path"""
    if not value.is_absolute():
        msg = 'Path must be absolute'
        raise ValueError(msg)
    return value


def validate_make_dir(value: Path) -> Path:
    """Returns existsing directory"""
    if value.exists():
        if not value.is_dir():
            msg = f'{value} exists and is not directory'
            raise ValueError(msg)
    else:
        value.mkdir(parents=True)
    return value


def validate_log_level(value: str) -> str:
    value = value.upper()
    if value not in {'DEBUG', 'INFO', 'WARN', 'WARNING', 'ERROR', 'CRITICAL'}:
        dosa = f'Unexpected log level {value}'
        raise ValueError(dosa)
    return value


MakeDirectoryPath = Annotated[Path, AfterValidator(validate_path_is_absolute), AfterValidator(validate_make_dir)]
LogLevelStr = Annotated[str, AfterValidator(validate_log_level)]


class Settings(BaseSettings):
    var_dir: MakeDirectoryPath = Path('/var/lib/saltbox-core/')
    cache_dir: MakeDirectoryPath = Path('/var/cache/saltbox-core/')
    taskiq_broker_url: str = ''
    log_level: LogLevelStr = 'info'
    basic_auth_username: str = ''
    basic_auth_password: str = ''
    base_url_root_path: str = '/'
    max_count: int = Field(default=1000, description='Max array length to request')
    origins: list[str] = Field(['*'], description='CORS allowed resources')
    is_module_inventory_on: bool = Field(default=False, description='Provide data for Inventory extension module')
    is_module_metric_on: bool = Field(default=False, description='Provide data for Metric extension module')

    # Auth and AuthZ
    keycloak_server_url: str = ''
    keycloak_front_url: str = ''
    keycloak_realm: str = ''
    keycloak_client: str = ''
    keycloak_client_secret: str = ''
    opa_url: str = ''

    # SLS and jobs repos
    gitlab_token: str | None = None
    gitlab_base_url: str = 'https://dev.saltbox.pro'
    gitlab_group_id: int | None = None
    local_repos_dir: MakeDirectoryPath = Field(
        Path('/var/lib/saltbox-core/repos/'),
        description='Salt modules cloned repos location',
    )
    salt_modules_serve_dir: MakeDirectoryPath = Field(
        Path('/srv/salt'),
        description='Ready-to-sync SLS files location',
    )
    salt_modules_permissions: TreePermissions | None = Field(
        default=None,
        description='Optional specification to force owner and permissions of SLS modules files in the serve_dir',
    )
    salt_modules_allow_duplicating_dirs: bool = Field(
        default=True, description='No error on duplicating directories in SLS modules'
    )
    sshfs_user: str = Field(default='saltbox', description='SSH user name to access files')
    salt_conf_user: str = Field(default='master', description='SSH user name to obtain modules for SaltStack')
    sshfs_dir: MakeDirectoryPath = Field(
        default=Path('/srv/sshfs/'),
        description='Path to store of files served by sshfs',
    )
    sshfs_permissions: TreePermissions | None = Field(
        default=None, description='Optional specification to force owner and permissions of Manifest.sshfs_files'
    )
    local_repo_sync_timeout_sec: int = 3600

    # GPG
    gpg_key_length: int = 4096
    gog_key_name_real: str = 'Saltbox'
    gpg_key_email: str = 'gpg@saltbox.pro'
    gpg_key_comment: str = 'This is a certificate for saltbox services'

    # PILLARS CRYPTO (encrypt-at-rest)
    pillars_kek_b64: str | None = Field(
        default=None,
        description='Base64-encoded 32-byte key for AES-256-GCM pillars encryption at rest',
    )
    pillars_kid: str = Field(
        default='core-kek-v1',
        description='Key identifier for pillars encryption (used for rotation)',
    )

    # TaskIQ
    taskiq_retry_default_retry_count: int = Field(default=3, description='TaskIQ retry default retry count')
    taskiq_retry_default_retry_label: bool = Field(default=False, description='TaskIQ retry default retry label')
    taskiq_retry_no_result_on_retry: bool = Field(default=True, description='TaskIQ retry no result on retry')
    taskiq_retry_default_delay: float = Field(default=5, description='TaskIQ retry default delay')
    taskiq_retry_use_jitter: bool = Field(default=False, description='TaskIQ retry use jitter')
    taskiq_retry_use_delay_exponent: bool = Field(default=False, description='TaskIQ retry use delay exponent')
    taskiq_retry_max_delay_exponent: float = Field(default=60, description='TaskIQ retry max delay exponent')

    # TASKS
    tasks_job_create_cooldown: int = Field(
        default=5, description='Number of seconds to wait from tasks job creation to new job'
    )
    tasks_defaults_batch_size: int = Field(title='Batch size', ge=0, default=0)
    tasks_defaults_max_jobs_count_at_same_time: int = Field(title='Max jobs count at some time', ge=1, default=1)
    tasks_defaults_max_retries: int = Field(title='Max retries', ge=0, default=1)
    tasks_defaults_retry_delay: int = Field(title='Retry delay', description='in seconds', ge=0, default=10)

    # JOBS
    jobs_max_ttl: int = Field(title='Max Job TTL', ge=0, default=60 * 60 * 24 * 7)
    jobs_default_ttl: int = Field(title='Default Job TTL', ge=0, default=60 * 60 * 24 * 7)
    jobs_return_data_expire_ttl: int = Field(
        default=60 * 60 * 24 * 30, description='Job return data expiration time in seconds'
    )

    # SALT BUFFER
    salt_buffer_manager_timeout: float = Field(default=0.1, description='Buffer manager timeout in seconds')
    salt_buffer_manager_batch_size: int = Field(default=100, description='Buffer manager batch size in bytes')
    salt_buffer_manager_event_process_retries: int = Field(
        default=3, description='Number of retries to process buffer manager event'
    )
    salt_taskiq_task_retries_count: int = Field(default=5, description='Number of retries to process taskiq task')

    model_config = SettingsConfigDict(env_file=ENV_FILE, extra='ignore')

    @computed_field  # type: ignore[prop-decorator]
    @cached_property
    def sshfs_tmp_dir(self) -> DirectoryPath:
        path = self.cache_dir / 'sshfs'
        if path.exists():
            remove_older_than(path, CACHE_LIFETIME, logging.WARNING)
        else:
            path.mkdir(parents=True)
        return path

    @property
    def keycloak_oidc_url(self) -> str:
        return f'{self.keycloak_server_url}/realms/{self.keycloak_realm}/.well-known/openid-configuration'

    @property
    def keycloak_authorization_endpoint(self) -> str:
        return f'{self.keycloak_front_url}/realms/{self.keycloak_realm}/protocol/openid-connect/auth'

    @property
    def keycloak_token_url(self) -> str:
        return f'{self.keycloak_front_url}/realms/{self.keycloak_realm}/protocol/openid-connect/token'

    @property
    def taskiq_redis_url(self) -> str:
        return self.taskiq_broker_url


SETTINGS = Settings()

_main_logger_name = __name__.split('.')[0]


class LogConfig(BaseModel):
    LOG_FORMAT: str = '%(levelprefix)s [%(filename)s:%(lineno)d] %(message)s'
    LOG_LEVEL: str = SETTINGS.log_level.upper()

    version: int = 1
    disable_existing_loggers: bool = False
    formatters: dict = {
        'default': {
            '()': 'uvicorn.logging.DefaultFormatter',
            'datefmt': '%Y-%m-%d %H:%M:%S',
            'fmt': LOG_FORMAT,
        },
    }
    handlers: dict = {
        'default': {
            'class': 'logging.StreamHandler',
            'formatter': 'default',
            'stream': 'ext://sys.stderr',
        },
    }
    loggers: dict = {
        _main_logger_name: {
            'handlers': ['default'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
    }


LOG_CONFIG = LogConfig()

logging.config.dictConfig(LOG_CONFIG.model_dump())

logger = logging.getLogger(_main_logger_name)
