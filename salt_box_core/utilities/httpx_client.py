from collections.abc import AsyncGenerator

import httpx

from salt_box_core.config import logger


class AsyncHttpxClientSingleton:
    """Singleton for HTTPX AsyncClient."""

    httpx_client: httpx.AsyncClient | None = None

    def __new__(cls) -> 'AsyncHttpxClientSingleton':
        if not hasattr(cls, 'instance'):
            cls.instance = super().__new__(cls)
            cls.instance.httpx_client = httpx.AsyncClient()
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
