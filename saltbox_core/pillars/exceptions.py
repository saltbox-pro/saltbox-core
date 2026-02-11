from fastapi import status

from saltbox_core.exceptions import CoreException


class PillarException(CoreException):
    """Base exception for Pillar errors."""

    detail: str = 'An error occurred in the Pillar service.'


class PillarAlreadyExistsException(PillarException):
    """Exception raised when attempting to create a pillar that already exists."""

    status_code: int = status.HTTP_409_CONFLICT
    detail: str = 'The specified pillar already exists.'


class PillarCreatedByRequiredException(PillarException):
    """Exception raised when attempting to create a personal pillar without created_by field."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    detail: str = 'The created_by field is required.'
