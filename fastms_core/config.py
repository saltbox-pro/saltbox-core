from typing import Any, Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_NAME = 'FastMS Core'


class Settings(BaseSettings):
    celery_broker_url: str | None = None
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
    salt_eauth: str = 'file'
    salt_password: str
    salt_url: str
    salt_username: str

    model_config = SettingsConfigDict(env_file='.env')

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


class LogConfig(BaseModel):
    LOG_FORMAT: str = '%(levelprefix)s %(message)s'
    LOG_LEVEL: str = 'INFO'

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
        'fastms_core': {'handlers': ['default'], 'level': LOG_LEVEL},
    }


SETTINGS = Settings()
LOG_CONFIG = LogConfig(LOG_LEVEL='DEBUG' if SETTINGS.debug else 'INFO')
