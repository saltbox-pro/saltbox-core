import abc

from typing import Any, Optional

from fastapi import HTTPException


class BaseHttpError(abc.ABC, HTTPException):
    @property
    @abc.abstractmethod
    def CODE(self) -> int: ...

    def __init__(self, detail: Any, headers: Optional[dict[str, str]] = None):
        super().__init__(status_code=self.CODE, detail=detail, headers=headers)


class BadRequest(BaseHttpError):
    """ Bad client data, e.g. on POST data validation error """
    CODE = 400


class Unauthorized(BaseHttpError):
    """ Failed to authorize """
    CODE = 401


class Forbidden(BaseHttpError):
    """ Access denied """
    CODE = 403


class NotFound(BaseHttpError):
    """ Resource is missing """
    CODE = 404


class MethodNotAllowed(BaseHttpError):
    """ Bad request type, e.g. POST on exclusively GET endpoint """
    CODE = 405


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
