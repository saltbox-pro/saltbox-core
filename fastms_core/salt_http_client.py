import asyncio
import contextlib
import logging

from datetime import datetime, timedelta
from functools import wraps
from pprint import pformat
from typing import Awaitable, Optional

import httpx
import pydantic
import ssl

from fastms_core.models.salt import AuthResponse

LOGGER = logging.getLogger(__name__)
DEBUG_INDENT = 2
RETRIES_ON_AUTH_ERROR = 1


class SaltHttpClientError(RuntimeError):
    ...


class SaltHttpClientConnectionError(SaltHttpClientError):
    ...


class SaltHttpClientBadResponse(SaltHttpClientError):
    """ Raises on bad HTTP response (4XX, 5XX codes) """


class SaltHttpClientUnauthorized(SaltHttpClientBadResponse):
    ...


class SaltHttpClient:
    """ SaltStack CherryPy Rest API client """
    TOKEN_BEST_BEFORE_SEC = 60

    def __init__(
        self,
        salt_instance: str,
        username: str,
        password: str,
        eauth: str,
        strict_ssl=True,
    ) -> None:
        self._login_data = {
            'username': username,
            'password': password,
            'eauth': eauth,
        }
        self._http = httpx.AsyncClient(
            base_url=salt_instance,
            headers={'Accept': 'application/json', },
            verify=strict_ssl,
            proxies=None,
        )
        self._token_expire = datetime.fromtimestamp(0.0)
        self._loop = asyncio.get_event_loop()

    def __del__(self):
        self._loop.run_until_complete(self._http.aclose())
        self._loop.close()

    def token_expires_in(self, seconds: int) -> bool:
        return self._token_expire - datetime.now() < timedelta(seconds=seconds)

    @property
    def token_expires(self) -> bool:
        return self.token_expires_in(self.TOKEN_BEST_BEFORE_SEC)

    async def _login(self) -> None:
        try:
            resp = await self._http.post(url='login', data=self._login_data)
        except (httpx.HTTPError, ssl.SSLCertVerificationError) as error:
            msg = str(error)
            if not msg:
                msg = type(error).__name__
            raise SaltHttpClientConnectionError(msg) from error

        self._raise_for_status(resp)

        try:
            body = AuthResponse.model_validate_json(resp.text)
        except pydantic.ValidationError as err:
            raise SaltHttpClientBadResponse(err)
        ret = body.return_[0]
        self._token_expire = datetime.fromtimestamp(ret.expire)

    @staticmethod
    def _login_decorator(fn):
        @wraps(fn)
        async def wrapper(self: 'SaltHttpClient', *args, **kwargs) -> Awaitable:
            if self.token_expires:
                LOGGER.info(
                    'Authenticate salt client due to token expiration time %s',
                    self._token_expire.isoformat())
                await self._login()
            for try_n in range(1 + RETRIES_ON_AUTH_ERROR):
                if try_n > 0:
                    LOGGER.warning(
                        'Try %i to reauthenticate salt client after authorization error',
                        try_n)
                    await self._login()
                with contextlib.suppress(SaltHttpClientUnauthorized):
                    return await fn(self, *args, **kwargs)
            raise SaltHttpClientUnauthorized('Failed to authenticate client')

        return wrapper

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code == 401:
            raise SaltHttpClientError('Unexpectedly unauthorized')
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            raise SaltHttpClientBadResponse(error)

    @staticmethod
    def _log_response(response: httpx.Response) -> None:
        LOGGER.debug(
            'Response headers:\n%s',
            pformat(dict(response.headers), indent=DEBUG_INDENT))
        LOGGER.debug('Response body:\n%s', response.content.decode())

    @_login_decorator
    async def run_job(
        self,
        tgt: str,
        fun: str,
        arg: Optional[list] = None,
        kwarg: Optional[dict] = None,
        tgt_type='glob',
    ) -> dict[str, list]:
        if arg is None:
            arg = []
        if kwarg is None:
            kwarg = {}
        data = {
            'arg': arg,
            'client': 'local_async',
            'fun': fun,
            'kwarg': kwarg,
            'tgt': tgt,
            'tgt_type': tgt_type,
        }

        try:
            resp = await self._http.post(url='jobs', data=data)
        except (httpx.HTTPError, ssl.SSLCertVerificationError) as error:
            msg = str(error)
            if not msg:
                msg = type(error).__name__
            raise SaltHttpClientConnectionError(msg)

        self._log_response(resp)
        self._raise_for_status(resp)
        return resp.json()
