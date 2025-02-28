import logging.config
from typing import Any, Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_NAME = 'Salt.box Core'


class Settings(BaseSettings):
    celery_broker_url: str | None = None
    celery_beat_schedule_filename: str = '/var/fastms-core/beat_schedule'
    debug: bool = False
    max_count: int = Field(default=1000, description='Max array length to request')
    mongo_db: str
    mongo_password: str
    mongo_port: int = 27017
    mongo_user: str
    origins: list[str] = Field(['*'], description='CORS allowed resources')
    redis_ca_cert: str | None = Field(None, description='Path to file of concatenated PEM certs')
    redis_password: str | None = None
    redis_tls_verification: Literal['none', 'optional', 'required'] = 'required'
    redis_url: str
    redis_username: str | None = None
    keycloak_server_url: str
    keycloak_front_url: str
    keycloak_realm: str
    keycloak_audience: str = 'account'
    keycloak_algorithm: str = 'RS256'
    keycloak_client: str
    opa_url: str
    salt_func_repo_url: str = 'https://dev.altlab.su/a.baikov/salt-func-schemas.git'
    salt_func_local_repo_name: str = 'salt-func-schemas'
    local_repos_path: str = 'repos'

    model_config = SettingsConfigDict(env_file='.env')

    @property
    def keycloak_jwks_uri(self) -> str:
        return f'{self.keycloak_server_url}/realms/{self.keycloak_realm}/protocol/openid-connect/certs'

    @property
    def keycloak_userinfo_url(self) -> str:
        return f'{self.keycloak_front_url}/realms/{self.keycloak_realm}/protocol/openid-connect/userinfo'

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


SETTINGS = Settings()


class LogConfig(BaseModel):
    LOG_FORMAT: str = '%(levelprefix)s [%(filename)s] %(message)s'
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
