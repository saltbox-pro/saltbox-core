import logging

from datetime import datetime, timedelta
from functools import wraps
from pprint import pformat
from typing import Optional

import httpx
import pydantic
import ssl

from app.models.salt import AuthResponse


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


def salt_http_client_login(fn):
    @wraps(fn)
    async def wrapper(self: 'SaltHttpClient', *args, **kwargs):
        if not self._token or self.token_expires:
            LOGGER.info('Authenticate salt client due missing or expiring token')
            await self._login()
        for _ in range(1 + RETRIES_ON_AUTH_ERROR):
            try:
                return await fn(self, *args, **kwargs)
            except SaltHttpClientUnauthorized:
                LOGGER.warning('Try to reauthenticate salt client after authorization error')
                await self._login()
    return wrapper


class SaltHttpClient:
    """ SaltStack CherryPy Rest API client """
    TOKEN_HEADER = 'X-Auth-Token'
    TOKEN_BEST_BEFORE_SEC = 3600

    def __init__(
        self,
        salt_instance: str,
        username: str,
        password: str,
        strict_ssl=True,
        eauth='rest'
    ) -> None:
        self._client_kwargs = {
            'verify': strict_ssl,
        }
        self._instance = salt_instance
        self._login_data = {
            'username': username,
            'password': password,
            'eauth': eauth,
        }
        self._default_headers = {
            'Accept': 'application/json',
        }
        self._http: Optional[httpx.AsyncClient] = None  # TODO Use or delete
        self._token = ''
        self._token_expire = datetime.fromtimestamp(0.0)

    def token_expires_in(self, seconds) -> bool:
        return datetime.now() - self._token_expire < timedelta(seconds=seconds)

    @property
    def token_expires(self) -> bool:
        return self.token_expires_in(self.TOKEN_BEST_BEFORE_SEC)

    def get_url(self, endpoint: str) -> str:
        return f'{self._instance}/{endpoint}'

    async def _login(self) -> None:
        if self._http is not None:
            await self._http.aclose()
        self._http = httpx.AsyncClient(**self._client_kwargs)
        self._default_headers.pop(self.TOKEN_HEADER, None)

        try:
            resp = await self._http.post(
                url=self.get_url('login'),
                headers=self._default_headers,
                data=self._login_data)
        except (httpx.HTTPError, ssl.SSLCertVerificationError) as error:
            msg = str(error)
            if not msg:
                msg = type(error).__name__
            raise SaltHttpClientConnectionError(msg) from error

        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as error:
            raise SaltHttpClientBadResponse(error)

        try:
            body = AuthResponse.model_validate_json(resp.text)
        except pydantic.ValidationError as err:
            raise SaltHttpClientBadResponse(err)
        ret = body.return_[0]
        self._token = ret.token
        self._token_expire = datetime.fromtimestamp(ret.expire)
        self._default_headers[self.TOKEN_HEADER] = self._token

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code == 401:
            raise SaltHttpClientError('Unexpectedly unauthorized')
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            raise SaltHttpClientBadResponse(error)

    @salt_http_client_login
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
            async with httpx.AsyncClient(**self._client_kwargs) as http:
                resp = await http.post(
                    url=self.get_url('jobs'),
                    headers=self._default_headers,
                    data=data)
        except (httpx.HTTPError, ssl.SSLCertVerificationError) as error:
            msg = str(error)
            if not msg:
                msg = type(error).__name__
            raise SaltHttpClientConnectionError(msg)

        LOGGER.debug('Response headers:\n%s', pformat(dict(resp.headers), indent=DEBUG_INDENT))
        LOGGER.debug('Response body:\n%s', resp.content.decode())

        self._raise_for_status(resp)
        return resp.json()
