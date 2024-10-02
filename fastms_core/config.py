from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

APP_NAME = 'FastMS core'


class Settings(BaseSettings):
    salt_url: str
    salt_username: str
    salt_password: str
    salt_eauth: str = 'file'
    redis_url: str
    debug: bool = False
    origins: list[str] = Field(['*'], description='CORS allowed resources')
    max_count: int = Field(default=1000, description='Max array length to request')


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


SETTINGS = Settings(_env_file='.env')
LOG_CONFIG = LogConfig(LOG_LEVEL='DEBUG' if SETTINGS.debug else 'INFO')
