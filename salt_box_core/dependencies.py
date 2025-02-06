import json
from typing import Annotated, Any

import httpx
import jwt
from aiocache import Cache  # type: ignore[import-untyped]
from fastapi import Depends, HTTPException, status
from fastapi.security import OpenIdConnect
from pydantic import ValidationError

from salt_box_core.config import SETTINGS, logger
from salt_box_core.db.mongo.schemas_base import User

# TODO (a.baikov): use redis cache
# user_cache = Cache.from_url(f'{SETTINGS.redis_url}?namespace=user&ttl=180', **SETTINGS.redis_connection_kwargs)
user_cache = Cache(ttl=180, namespace='user')


keycloak_scheme = OpenIdConnect(
    openIdConnectUrl=SETTINGS.well_known_url,
    scheme_name='KeycloakOIDC',
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


async def get_current_user(bearer: Annotated[str | None, Depends(keycloak_scheme)]) -> User:
    if bearer is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Not authenticated',
            headers={'WWW-Authenticate': 'Bearer'},
        )

    user = await user_cache.get(bearer)
    if user:
        return User(**json.loads(user))

    headers = {'Authorization': bearer}
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(SETTINGS.keycloak_userinfo_url, headers=headers)
            response.raise_for_status()
            await user_cache.set(bearer, response.text)

            logger.debug('user: %s', user)

            return User(**response.json())
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=e.response.status_code,
                detail='Could not validate credentials',
                headers={'WWW-Authenticate': 'Bearer'},
            ) from None


async def get_current_user_from_jwt(token: Annotated[str | None, Depends(keycloak_scheme)]) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail='Could not validate credentials',
        headers={'WWW-Authenticate': 'Bearer'},
    )
    if token is None:
        raise credentials_exception from None

    try:
        access_token = token.replace('Bearer ', '')
        payload = await decode_jwt(access_token)
        user_id: str = payload.get('sub')
        if user_id is None:
            raise credentials_exception from None
    except (jwt.InvalidTokenError, ValidationError):
        raise credentials_exception from None
    except jwt.PyJWKClientError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Get signing key from JWKS URI failed',
            headers={'WWW-Authenticate': 'Bearer'},
        ) from None

    user = User(**payload)
    if user is None:
        raise credentials_exception from None

    return user
