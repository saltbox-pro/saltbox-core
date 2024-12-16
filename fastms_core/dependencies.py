import logging.config
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import ValidationError

from fastms_core.config import LOG_CONFIG, SETTINGS
from fastms_core.db.mongo.schemas_base import User

logging.config.dictConfig(LOG_CONFIG.model_dump())

logger = logging.getLogger(__name__)

keycloak_scheme = HTTPBearer(
    scheme_name='Keycloak JWT',
    description='Validate JWT token from Keycloak server with JWKS URI and extract user data',
)


# Использование PyJWKClient обеспечивает автоматическое кэширование публичных ключей,
# что позволяет минимизировать количество запросов к JWKS URI.
jwks_client = jwt.PyJWKClient(uri=SETTINGS.keycloak_jwks_uri)


async def decode_jwt(token: str) -> Any:
    signing_key = jwks_client.get_signing_key_from_jwt(token)
    payload = jwt.decode(
        token, signing_key.key, algorithms=[SETTINGS.keycloak_algorithm], audience=SETTINGS.keycloak_audience
    )
    return payload


async def get_current_user(token: Annotated[HTTPAuthorizationCredentials, Depends(keycloak_scheme)]) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail='Could not validate credentials',
        headers={'WWW-Authenticate': 'Bearer'},
    )
    try:
        payload = await decode_jwt(token.credentials)
        user_id: str = payload.get('sub')
        if user_id is None:
            raise credentials_exception from None
    except (jwt.InvalidTokenError, ValidationError):
        raise credentials_exception from None
    user = User(**payload)
    if user is None:
        raise credentials_exception from None

    return user


class RolesRequiredDependency:
    def __init__(self, roles: list[str]):
        self.roles = roles

    def __call__(self, user: Annotated[User, Depends(get_current_user)]) -> User:
        if not any(role in user.realm_access.roles for role in self.roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail='Not enough permissions',
                headers={'WWW-Authenticate': 'Bearer'},
            )
        return user
