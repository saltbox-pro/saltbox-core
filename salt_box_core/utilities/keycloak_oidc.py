import json
import time
from contextvars import ContextVar
from typing import Any, cast

import httpx
import jwt
from fastapi import Request, status
from pydantic import ValidationError
from redis.asyncio import Redis

from salt_box_core.config import SETTINGS, logger
from salt_box_core.utilities.httpx_client import get_httpx_async_client
from salt_box_core.utilities.redis_cache import CustomRedisCache
from saltbox_sdk.db.redis.config import get_redis_now

request_context: ContextVar[Request] = ContextVar('request_context')


class KeycloakOIDCError(Exception):
    """Base class for Keycloak OIDC errors."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message


class KeycloakOIDC:
    """Keycloak OIDC client singleton.
    Initializes only once and caches OIDC configuration and keys.
    """

    def __init__(self, audience: str = 'account') -> None:
        logger.debug('Initializing KeycloakOIDC instance.')
        self._oidc_url = SETTINGS.keycloak_oidc_url
        self._httpx_client = get_httpx_async_client()
        self._redis: Redis = get_redis_now()
        self._oidc_config_cache = CustomRedisCache(redis=self._redis, namespace='oidc_config')
        self._jwks_cache = CustomRedisCache(redis=self._redis, namespace='oidc_jwks')
        self._kid_key_cache = CustomRedisCache(redis=self._redis, namespace='oidc_kid_key')
        self._token_cache = CustomRedisCache(redis=self._redis, namespace='oidc_token')
        self._issuer: str | None = None
        self._audience = audience
        self._algorithms = ['RS256']
        self._token_url: str | None = None
        self._authorization_endpoint: str | None = None

    @property
    def authorization_endpoint(self) -> str:
        if not self._authorization_endpoint:
            raise KeycloakOIDCError(status.HTTP_401_UNAUTHORIZED, 'Authorization URL not found in OIDC config.')

        return self._authorization_endpoint

    @property
    def token_url(self) -> str:
        if not self._token_url:
            raise KeycloakOIDCError(status.HTTP_401_UNAUTHORIZED, 'Token URL not found in OIDC config.')

        return self._token_url

    # TODO (a.baikov): Deprecated
    async def init_config(self) -> None:
        logger.debug('Initializing KeycloakOIDC configuration.')
        oidc_config = await self._get_oidc_config()
        self._token_url = oidc_config.get('token_endpoint')
        self._authorization_endpoint = oidc_config.get('authorization_endpoint')
        logger.debug('Token URL: %s, Auth URL: %s', self._token_url, self._authorization_endpoint)

    async def _get_oidc_config(self) -> dict[str, Any]:
        """Get OIDC configuration from Keycloak server and cache it.

        Returns:
            dict[str, Any]: OIDC configuration.
        """
        oidc_config = await self._oidc_config_cache.get(self._oidc_url)
        if oidc_config:
            logger.debug('OIDC config loaded from cache.')
            return cast(dict[str, Any], json.loads(oidc_config))

        try:
            logger.debug('Fetching OIDC config from URL: %s', self._oidc_url)
            response = await self._httpx_client.get(self._oidc_url)
            response.raise_for_status()

            oidc_config = response.json()
            self._issuer = oidc_config.get('issuer')
            if not self._issuer:
                raise KeycloakOIDCError(status.HTTP_401_UNAUTHORIZED, 'Issuer not found in OIDC config.')

            self._algorithms = oidc_config.get('id_token_signing_alg_values_supported', self._algorithms)

            logger.debug('OIDC config fetched successfully: %s - %s', self._issuer, self._algorithms)

            await self._oidc_config_cache.set(self._oidc_url, json.dumps(oidc_config))
            return cast(dict, oidc_config)
        except httpx.HTTPStatusError as e:
            logger.warning('Error fetching OIDC config: %s', e)
            raise KeycloakOIDCError(
                status.HTTP_503_SERVICE_UNAVAILABLE, 'Error fetching OIDC config. Keycloak server is unavailable.'
            ) from None
        except httpx.ReadTimeout as e:
            logger.error('Timeout error fetching OIDC config: %s', e)
            raise KeycloakOIDCError(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                'Timeout error fetching OIDC config. Keycloak server is unavailable.',
            ) from None
        except Exception as e:
            logger.exception('Unexpected error fetching OIDC config: %s', e)
            raise KeycloakOIDCError(
                status.HTTP_500_INTERNAL_SERVER_ERROR, 'Unexpected error fetching OIDC config'
            ) from None

    async def _get_key_by_kid(self, token_kid: str) -> jwt.PyJWK:
        """Get the public key by KID from the JWKS and cache it.

        Args:
            token_kid (str): The KID of the token.

        Returns:
            jwt.PyJWK: The public key.
        """
        cached_key = await self._kid_key_cache.get(token_kid)
        if cached_key:
            logger.debug('Key loaded from cache')
            return jwt.PyJWK(json.loads(cached_key))

        jwks = await self._get_jwks()
        public_keys = {key['kid']: key for key in jwks['keys']}
        if token_kid not in public_keys:
            raise KeycloakOIDCError(status.HTTP_401_UNAUTHORIZED, 'Key not found in JWKS.')

        await self._kid_key_cache.set(token_kid, json.dumps(public_keys[token_kid]))
        logger.debug('Key cached successfully: %s', token_kid)
        return jwt.PyJWK(public_keys[token_kid])

    async def _get_jwks(self) -> dict[str, Any]:
        """Get the JWKS from the OIDC configuration and cache it.

        Returns:
            dict[str, Any]: The JWKS.
        """
        oidc_config = await self._get_oidc_config()
        jwks_uri = oidc_config.get('jwks_uri')
        if not jwks_uri:
            raise KeycloakOIDCError(status.HTTP_401_UNAUTHORIZED, 'JWKS URI not found in OIDC config.')
        cached_jwks = await self._jwks_cache.get(jwks_uri)
        if cached_jwks:
            logger.debug('JWKS loaded from cache.')
            return cast(dict[str, Any], json.loads(cached_jwks))

        try:
            logger.debug('Fetching JWKS from URL: %s', jwks_uri)
            response = await self._httpx_client.get(jwks_uri)
            response.raise_for_status()

            jwks = response.json()

            await self._jwks_cache.set(jwks_uri, json.dumps(jwks))
            logger.debug('JWKS cached successfully with uri: %s', jwks_uri)
            return cast(dict[str, Any], jwks)
        except httpx.HTTPStatusError as e:
            logger.warning('Error fetching JWKS: %s', e)
            raise KeycloakOIDCError(
                status.HTTP_503_SERVICE_UNAVAILABLE, 'Error fetching JWKS. Keycloak server is unavailable.'
            ) from None
        except httpx.ReadTimeout as e:
            logger.warning('Timeout error fetching JWKS: %s', e)
            raise KeycloakOIDCError(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                'Timeout error fetching JWKS. Keycloak server is unavailable.',
            ) from None

    async def decode_jwt(self, token: str | None) -> dict[str, str | list[str]]:
        """Decode the JWT token and verify its signature.

        Args:
            token (str | None): The JWT token to decode.
        Returns:
            dict[str, str | list[str]]: The decoded token.
        Raises:
            KeycloakOIDCError: If the token is invalid or expired.
        """
        if not token or not token.startswith('Bearer '):
            raise KeycloakOIDCError(status.HTTP_401_UNAUTHORIZED, 'Authorization header is missing or invalid.')
        token = token.removeprefix('Bearer').strip()

        cached_token = await self._token_cache.get(token)
        if cached_token:
            logger.debug('Token loaded from cache.')
            return cast(dict[str, str | list[str]], json.loads(cached_token))

        try:
            unverified_header = jwt.get_unverified_header(token)
        except jwt.DecodeError as e:
            logger.warning('Decode error for JWT token header: %s', e)
            raise KeycloakOIDCError(status.HTTP_401_UNAUTHORIZED, 'Decode error for JWT token header.') from None
        token_kid = unverified_header.get('kid')
        if not token_kid:
            raise KeycloakOIDCError(status.HTTP_401_UNAUTHORIZED, 'KID not found in token.')

        key = await self._get_key_by_kid(token_kid)

        logger.debug('Start Decoding JWT token.')

        try:
            decoded_token = jwt.decode(
                token,
                key=key,
                issuer=self._issuer,
                algorithms=self._algorithms,
                audience=self._audience,
                options={
                    'verify_iss': True,
                    'verify_signature': True,
                    'verify_aud': True,
                    'verify_iat': True,
                    'require_exp': True,
                },
            )
            logger.debug('Token decoded successfully. User: %s', decoded_token['name'])
            current_time = int(time.time())
            exp_time = decoded_token.get('exp', 0)
            ttl = max(0, exp_time - current_time)  # Ensure TTL is never negative

            logger.debug('Set token cache with ttl: %s', ttl)
            await self._token_cache.set(token, json.dumps(decoded_token), ttl=ttl)
            return cast(dict[str, str | list[str]], decoded_token)
        except jwt.ExpiredSignatureError:
            logger.warning('Token expired.')
            raise KeycloakOIDCError(status.HTTP_401_UNAUTHORIZED, 'Token has expired') from None
        except jwt.InvalidTokenError as e:
            logger.warning('Invalid token: %s', e)
            raise KeycloakOIDCError(status.HTTP_401_UNAUTHORIZED, f'Invalid token: {e!s}') from None
        except ValidationError as e:
            logger.warning('Token validation error: %s', e)
            raise KeycloakOIDCError(status.HTTP_401_UNAUTHORIZED, 'Token validation error') from None
        except Exception as e:
            logger.exception('Unexpected error: %s', e)
            raise KeycloakOIDCError(status.HTTP_500_INTERNAL_SERVER_ERROR, 'Unexpected error') from e


class KeycloakOIDCFactory:
    """Singleton factory for KeycloakOIDC."""

    _instance: KeycloakOIDC | None = None

    @classmethod
    def get_instance(cls) -> KeycloakOIDC:
        if cls._instance is None:
            cls._instance = KeycloakOIDC()
        return cls._instance
