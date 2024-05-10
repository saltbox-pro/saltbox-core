from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    salt_url: str
    salt_username: str
    salt_password: str
    redis_url: str


SETTINGS = Settings(_env_file='.env')
