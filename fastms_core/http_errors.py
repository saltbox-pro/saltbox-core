from __future__ import annotations

import abc

from typing import Any

from fastapi import HTTPException, WebSocketException
from starlette import status


class BaseHttpError(abc.ABC, HTTPException):
    @property
    @abc.abstractmethod
    def CODE(self) -> int: ...

    def __init__(self, detail: Any, headers: dict[str, str] | None = None):
        super().__init__(status_code=self.CODE, detail=detail, headers=headers)


class BadRequest(BaseHttpError):
    """ Bad client data, e.g. on POST data validation error """
    CODE = status.HTTP_400_BAD_REQUEST


class Unauthorized(BaseHttpError):
    """ Failed to authorize """
    CODE = status.HTTP_401_UNAUTHORIZED


class Forbidden(BaseHttpError):
    """ Access denied """
    CODE = status.HTTP_403_FORBIDDEN


class NotFound(BaseHttpError):
    """ Resource is missing """
    CODE = status.HTTP_404_NOT_FOUND


class MethodNotAllowed(BaseHttpError):
    """ Bad request type, e.g. POST on exclusively GET endpoint """
    CODE = status.HTTP_405_METHOD_NOT_ALLOWED


class ImATeapot(BaseHttpError):
    """ Teapot requested to make coffee """
    CODE = 418


class InternalServerError(BaseHttpError):
    """ Generic server-side error """
    CODE = 500


class NotImplemented(BaseHttpError):
    """ Such request can not be processed yet """
    CODE = 501


class BadGateway(BaseHttpError):
    """ Invalid response from an upstream server """
    CODE = 502


class ServiceUnavalable(BaseHttpError):
    """ Server not able to handle the request now """
    CODE = 503


class WebSocketError(abc.ABC, WebSocketException):
    @property
    @abc.abstractmethod
    def CODE(self) -> int: ...

    def __init__(self, reason: str | None = None) -> None:
        super().__init__(code=self.CODE, reason=reason)


class WebSocketPolicyViolation(WebSocketError):
    """ Generic error means message violates policy of socket """
    CODE = status.WS_1008_POLICY_VIOLATION


class WebSocketServerError(WebSocketError):
    """ Unexpected conditions prevents from fulfilling a request """
    CODE = status.WS_1011_INTERNAL_ERROR
