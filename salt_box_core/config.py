import logging.config
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from salt_box_core.utilities.filesystem import recursive_force_remove

APP_NAME = 'Salt.Box Core'
APP_DESC = 'Salt.Box Core API'


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


def validate_empty_dir(value: Path) -> Path:
    """
    Returns existsing empty directory

    BE CAREFUL TO NOT TO LOSE DATA
    """
    created = validate_make_dir(value)
    for path in created.glob('*'):
        recursive_force_remove(path)
    return created


MakeDirectoryPath = Annotated[Path, AfterValidator(validate_path_is_absolute), AfterValidator(validate_make_dir)]
EmptyDirectoryPath = Annotated[Path, AfterValidator(validate_path_is_absolute), AfterValidator(validate_empty_dir)]


class Settings(BaseSettings):
    var_dir: MakeDirectoryPath = Path('/var/lib/saltbox-core/')
    taskiq_broker_url: str = ''
    debug: bool = False
    show_docs: bool = False
    basic_auth_username: str = ''
    basic_auth_password: str = ''
    base_url_root_path: str = '/'
    max_count: int = Field(default=1000, description='Max array length to request')
    mongo_db: str = ''
    mongo_password: str | None = None
    mongo_port: int = 27017
    mongo_user: str = ''
    origins: list[str] = Field(['*'], description='CORS allowed resources')
    redis_ca_cert: str | None = Field(None, description='Path to file of concatenated PEM certs')
    redis_password: str | None = None
    redis_tls_verification: Literal['none', 'optional', 'required'] = 'required'
    redis_url: str = ''
    redis_username: str | None = None
    keycloak_server_url: str = ''
    keycloak_front_url: str = ''
    keycloak_realm: str = ''
    keycloak_client: str = ''
    keycloak_client_secret: str = ''
    opa_url: str = ''
    salt_func_repo_url: str = 'https://dev.saltbox.pro/saltbox/salt-func-schemas.git'
    salt_func_local_repo_name: str = 'salt-func-schemas'
    local_repos_dir: MakeDirectoryPath = Path('/srv/repos')
    sshfs_user: str = Field(default='saltbox', description='SSH user name to access files')
    gitfs_user: str = Field(default='git', description='SSH user name to access Git repos')
    sshfs_dir: MakeDirectoryPath = Field(
        default=Path('/srv/sshfs/'),
        description='Path to store of files served by sshfs',
    )
    cache_dir: MakeDirectoryPath = Path('/var/cache/saltbox-core/')
    sshfs_tmp_dir: EmptyDirectoryPath = cache_dir / 'sshfs'
    local_repo_sync_timeout_sec: int = 30
    rabbitmq_url: str = 'amqp://guest:guest@rabbitmq:5672'
    gpg_key_length: int = 4096
    gog_key_name_real: str = 'Saltbox'
    gpg_key_email: str = 'gpg@saltbox.pro'
    gpg_key_comment: str = 'This is a certificate for saltbox services'

    model_config = SettingsConfigDict(env_file='.env')

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
    def mongo_url(self) -> str:
        return f'mongodb://{self.mongo_user}:{self.mongo_password}@mongo:{self.mongo_port}/'

    @property
    def redis_connection_kwargs(self) -> dict[str, Any]:
        """
        Additional options for redis.*.from_url() group of methods
        """
        result = {
            'username': self.redis_username,
            'password': self.redis_password,
        }
        if self.redis_url.startswith('rediss:'):
            result |= {
                'ssl_cert_reqs': self.redis_tls_verification,
                'ssl_ca_certs': self.redis_ca_cert,
            }
        return result

    @property
    def taskiq_redis_url(self) -> str:
        return self.taskiq_broker_url


SETTINGS = Settings()


class LogConfig(BaseModel):
    LOG_FORMAT: str = '%(levelprefix)s [%(filename)s:%(lineno)d] %(message)s'
    LOG_LEVEL: str = 'DEBUG' if SETTINGS.debug else 'INFO'

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
        'salt_box_core': {
            'handlers': ['default'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
    }


LOG_CONFIG = LogConfig()

logging.config.dictConfig(LOG_CONFIG.model_dump())

logger = logging.getLogger('salt_box_core')
