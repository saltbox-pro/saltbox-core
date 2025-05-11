from collections.abc import Awaitable, Callable
from contextvars import ContextVar

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from salt_box_core.config import logger
from salt_box_core.utilities.keycloak_oidc import KeycloakOIDCError, KeycloakOIDCFactory

RequestResponseEndpoint = Callable[[Request], Awaitable[Response]]
request_context: ContextVar[Request] = ContextVar('request_context')


class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: ASGIApp,
        excluded_paths: list[str] | None = None,
    ) -> None:
        super().__init__(app)
        logger.debug('Initializing AuthMiddleware.')
        self._oidc = KeycloakOIDCFactory.get_instance()
        self.excluded_paths = excluded_paths or []

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        logger.debug('Dispatching request: %s', request.url.path)
        if request.url.path in self.excluded_paths:
            return await call_next(request)

        token = request.headers.get('Authorization')

        try:
            decoded_token = await self._oidc.decode_jwt(token)
        except KeycloakOIDCError as e:
            return JSONResponse(status_code=e.status_code, content={'detail': e.message})
        request.state.user = decoded_token
        request_context.set(request)
        response = await call_next(request)
        return response
