from fastapi import status

from saltbox_core.exceptions import CoreException


class TaskServiceException(CoreException):
    """Base exception for TaskService."""

    detail: str = 'TaskService error occurred'


class TaskObjectDoesNotExistException(TaskServiceException):
    """Exception raised when a Task object does not exist."""

    status_code: int = status.HTTP_404_NOT_FOUND
    detail: str = 'Task object does not exist'


class TaskCreateSchemaValidationException(TaskServiceException):
    """Exception raised when TaskCreateSchema validation fails."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    detail: str = 'TaskCreateSchema validation failed'
