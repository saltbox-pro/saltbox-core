from typing import Any

from fastapi import HTTPException, WebSocketException, status


class BaseHttpError(HTTPException):
    _code: int

    def __init__(self, detail: Any, headers: dict[str, str] | None = None):
        super().__init__(status_code=self._code, detail=detail, headers=headers)


class BadRequest(BaseHttpError):
    """Bad client data, e.g. on POST data validation error"""

    _code = status.HTTP_400_BAD_REQUEST


class Unauthorized(BaseHttpError):
    """Failed to authorize"""

    _code = status.HTTP_401_UNAUTHORIZED


class Forbidden(BaseHttpError):
    """Access denied"""

    _code = status.HTTP_403_FORBIDDEN


class NotFound(BaseHttpError):
    """Resource is missing"""

    _code = status.HTTP_404_NOT_FOUND


class MethodNotAllowed(BaseHttpError):
    """Bad request type, e.g. POST on exclusively GET endpoint"""

    _code = status.HTTP_405_METHOD_NOT_ALLOWED


class ImATeapot(BaseHttpError):
    """Teapot requested to make coffee"""

    _code = 418


class UnprocessableEntity(BaseHttpError):
    """Server cannot process the request due to invalid data"""

    _code = status.HTTP_422_UNPROCESSABLE_ENTITY


class InternalServerError(BaseHttpError):
    """Generic server-side error"""

    _code = 500


class NotImplemented(BaseHttpError):
    """Such request can not be processed yet"""

    _code = 501


class BadGateway(BaseHttpError):
    """Invalid response from an upstream server"""

    _code = 502


class ServiceUnavalable(BaseHttpError):
    """Server not able to handle the request now"""

    _code = 503


class WebSocketError(WebSocketException):
    _code: int

    def __init__(self, reason: str | None = None) -> None:
        super().__init__(code=self._code, reason=reason)


class WebSocketPolicyViolation(WebSocketError):
    """Generic error means message violates policy of socket"""

    _code = status.WS_1008_POLICY_VIOLATION


class WebSocketServerError(WebSocketError):
    """Unexpected conditions prevents from fulfilling a request"""

    _code = status.WS_1011_INTERNAL_ERROR
