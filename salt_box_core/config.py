import logging.config
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, DirectoryPath, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_NAME = 'Salt.Box Core'
APP_DESC = 'Salt.Box Core API'


class Settings(BaseSettings):
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
    salt_func_repo_url: str = 'https://dev.saltbox.pro/a.baikov/salt-func-schemas.git'
    salt_func_local_repo_name: str = 'salt-func-schemas'
    local_repos_path: DirectoryPath = Path('/srv/repos')
    sshfs_path: DirectoryPath = Path('/srv/sshfs/')
    local_repo_sync_timeout_sec: int = 600
    rabbitmq_url: str = 'amqp://guest:guest@rabbitmq:5672'

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
        'salt_box_core': {'handlers': ['default'], 'level': LOG_LEVEL},
    }


LOG_CONFIG = LogConfig()

logging.config.dictConfig(LOG_CONFIG.model_dump())

logger = logging.getLogger(__name__)
