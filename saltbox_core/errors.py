from fastapi import status

from saltbox_sdk.fastapi_utils.errors import SaltBoxBaseError


class CoreError(SaltBoxBaseError):
    """Base class for all core-related exceptions."""

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    detail: str = 'An unexpected error occurred in the core service.'
