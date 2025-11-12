from fastapi import status

from saltbox_sdk.exceptions import SaltBoxBaseException


class CoreException(SaltBoxBaseException):
    """Base class for all core-related exceptions."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    detail: str = 'An unexpected error occurred in the core service.'


class UnsupportedSchemaTypeException(CoreException):
    """Exception raised for unsupported schema types."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    detail: str = 'Unsupported schema type provided.'


class GitlabApiException(CoreException):
    """Exception raised for GitLab API related errors."""

    status_code: int = status.HTTP_502_BAD_GATEWAY
    detail: str = 'An error occurred while communicating with the GitLab API.'


class FileNotFoundException(CoreException):
    status_code: int = status.HTTP_404_NOT_FOUND
    detail: str = 'File not found'
