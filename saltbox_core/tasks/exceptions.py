from fastapi import status

from saltbox_core.exceptions import CoreException


class TaskServiceException(CoreException):
    """Base exception for TaskService."""

    detail: str = 'TaskService error occurred'


class TaskCreateServiceException(TaskServiceException):
    """Base exception for TaskService."""

    detail: str = 'TaskService task create error occurred'


class TaskCreateSchemaValidationException(TaskServiceException):
    """Exception raised when TaskCreateSchema validation fails."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    detail: str = 'TaskCreateSchema validation failed'


class TaskTemplateNotFoundException(TaskServiceException):
    """Exception raised when a task template is not found."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    detail: str = 'Task template not found'

    def __init__(self, template_name: str | None = None):
        if template_name:
            self.detail = f'Task template with name "{template_name}" not found'
        super().__init__(detail=self.detail)
