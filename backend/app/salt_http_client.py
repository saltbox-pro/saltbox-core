import logging

from pprint import pformat
from typing import Optional

import httpx
import ssl


LOGGER = logging.getLogger(__name__)
DEBUG_INDENT = 2


class SaltHttpClientError(RuntimeError):
    ...


class SaltHttpClientConnectionError(SaltHttpClientError):
    ...


class SaltHttpClientBadResponse(SaltHttpClientError):
    """ Raises on bad HTTP response (4XX, 5XX codes) """


class SaltHttpClient:
    """ SaltStack Rest API client """
    def __init__(self, salt_instance: str, strict_ssl=True) -> None:
        self._client_kwargs = {
            'verify': strict_ssl,
        }
        self._instance = salt_instance

    def get_url(self, endpoint: str) -> str:
        return f'{self._instance}/{endpoint}'

    async def run_job(
        self,
        tgt: str,
        fun: str,
        arg: Optional[list] = None,
        kwarg: Optional[dict] = None,
        tgt_type='glob',
    ) -> str:
        if arg is None:
            arg = []
        if kwarg is None:
            kwarg = {}
        data = {
            'arg': arg,
            'client': 'local',
            'fun': fun,
            'kwarg': kwarg,
            'tgt': tgt,
            'tgt_type': tgt_type,
        }

        try:
            async with httpx.AsyncClient(**self._client_kwargs) as http:
                resp = await http.post(url=self.get_url('jobs'), data=data)
        except (httpx.HTTPError, ssl.SSLCertVerificationError) as error:
            msg = str(error)
            if not msg:
                msg = type(error).__name__
            raise SaltHttpClientConnectionError(msg) from error

        LOGGER.debug('Response headers:\n%s', pformat(dict(resp.headers), indent=DEBUG_INDENT))
        LOGGER.debug('Response body:\n%s', resp.content.decode())

        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as error:
            raise SaltHttpClientBadResponse(error)
        return resp.json()
