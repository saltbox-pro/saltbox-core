from collections.abc import AsyncGenerator

import httpx
from httpx import BasicAuth

from salt_box_core.config import SETTINGS, logger


class AsyncHttpxClientSingleton:
    """Singleton for HTTPX AsyncClient."""

    httpx_client: httpx.AsyncClient | None = None

    def __new__(cls) -> 'AsyncHttpxClientSingleton':
        if not hasattr(cls, 'instance'):
            cls.instance = super().__new__(cls)
            auth = None
            if SETTINGS.basic_auth_username != '' and SETTINGS.basic_auth_password != '':
                auth = BasicAuth(SETTINGS.basic_auth_username, SETTINGS.basic_auth_password)
            cls.instance.httpx_client = httpx.AsyncClient(auth=auth)
            logger.debug('HTTPX AsyncClient initialized.')
        return cls.instance


def get_httpx_async_client() -> httpx.AsyncClient:
    """Get the HTTPX AsyncClient singleton instance."""

    httpx_client = AsyncHttpxClientSingleton().httpx_client

    if httpx_client is None:
        msg = 'HTTPX client is not initialized.'
        raise RuntimeError(msg)
    return httpx_client


async def get_async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Get an HTTPX AsyncClient instance.

    This function is intended to be used as a dependency in FastAPI routes.
    It ensures that the client is properly instantiated and closed.

    Yields:
        AsyncClient: The HTTPX AsyncClient instance.

    Raises:
        RuntimeError: If the HTTPX client cannot be instantiated.
    """
    client = None
    try:
        client = get_httpx_async_client()
        logger.debug('Yielding HTTPX client.')
        yield client
    finally:
        pass
