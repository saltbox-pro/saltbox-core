from fastapi import status

from saltbox_core.exceptions import CoreException


class GitlabApiException(CoreException):
    """Base exception for GitLab API."""

    detail: str = 'GitLab API error occurred'


class MissingGroupIdException(GitlabApiException):
    """Exception raised when a GitLab group ID is missing."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    detail: str = 'GitLab group ID is missing in settings'


class GitlabApiTimeoutException(GitlabApiException):
    """Exception raised when a timeout occurs while waiting for a response from the GitLab API."""

    status_code: int = status.HTTP_504_GATEWAY_TIMEOUT
    detail: str = 'Execution is too long, try lesser count of load size or wait GitLab to boot'
