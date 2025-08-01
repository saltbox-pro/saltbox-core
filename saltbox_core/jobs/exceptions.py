from fastapi import status

from saltbox_core.exceptions import CoreException


class JobException(CoreException):
    """Base class for job-related exceptions."""

    detail: str = 'An error occurred in the job service.'


class JobDoesNotExistsException(JobException):
    """Exception raised when a job does not exist."""

    status_code: int = status.HTTP_404_NOT_FOUND
    detail: str = 'Job does not exist.'


class JobMultipleReturnsException(JobException):
    """Exception raised when multiple jobs are returned when only one is expected."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    detail: str = 'Multiple jobs found, expected only one.'


class JobCreateException(JobException):
    """Exception raised when there is an error creating a job."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    detail: str = 'Error creating job.'


class JobServiceInvalidArgsException(JobException):
    """Exception raised when invalid arguments are provided to the job service."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    detail: str = 'Invalid arguments provided to the job service.'


class JobServiceException(JobException):
    """Exception raised for general job service errors."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    detail: str = 'An error occurred in the job service.'
