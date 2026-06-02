from fastapi import status

from saltbox_core.exceptions import CoreException


class TaskTemplateException(CoreException):
    """Base exception for TaskTemplateService."""

    detail: str = 'TaskTemplateService error occurred'


class TaskTemplateCreateException(TaskTemplateException):
    """Base exception for TaskTemplateService."""

    detail: str = 'TaskTemplateService task create error occurred'


class TaskTemplateNotFoundException(TaskTemplateException):
    """Exception raised when a task template is not found."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    detail: str = 'Task template not found'

    def __init__(self, template_name: str | None = None):
        if template_name:
            self.detail = f'Task template with name "{template_name}" not found'
        super().__init__(detail=self.detail)


class RepoURLMissingException(TaskTemplateException):
    """Exception raised when a git repo source is missing the repo_url field."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    detail: str = 'Git repo source is missing repo_url field'

    def __init__(self, source_id: str | None = None):
        if source_id:
            self.detail = f'Git repo source with ID "{source_id}" is missing repo_url field'
        super().__init__(detail=self.detail)


class TaskTemplateSourceLockException(TaskTemplateException):
    """Exception raised when a task template source is locked."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    detail: str = 'Task template source is locked'

    def __init__(self, source_id: str | None = None):
        if source_id:
            self.detail = f'Task template source with ID "{source_id}" is locked'
        super().__init__(detail=self.detail)


class TaskTemplateSourceServeUpdateException(TaskTemplateException):
    """Exception raised when a task template source fails to update."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    detail: str = 'Task template source failed to update'


class ManifestFileSyncHttpException(TaskTemplateException):
    """Exception raised when syncing manifest file from HTTP source fails."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    detail: str = 'Failed to sync manifest file from HTTP source'

    def __init__(
        self,
        source_id: str | None = None,
        url: str | None = None,
        status_code: int | None = None,
        content: str | None = None,
        detail: str | None = None,
    ):
        if source_id:
            self.detail = f'Failed to sync manifest file from HTTP source with ID "{source_id}"'
        if url:
            self.detail += f' (URL: {url})'
        if status_code:
            self.detail += f' (Status code: {status_code})'
        if content:
            self.detail += f' (Content: {content})'
        if detail:
            self.detail += f' ({detail})'
        super().__init__(detail=self.detail)


class FileUploadException(TaskTemplateException):
    """Exception raised when an error occurs during file upload."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    detail: str = 'An error occurred during file upload'


class FileTypeNotSupportedException(TaskTemplateException):
    """Exception raised when an uploaded file has an unsupported type."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    detail: str = 'Uploaded file type is not supported'

    def __init__(self, ext: str | None = None):
        if ext:
            self.detail = f'Uploaded file type "{ext}" is not supported'
        super().__init__(detail=self.detail)


class FileNameMissingException(TaskTemplateException):
    """Exception raised when an uploaded file is missing a filename."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    detail: str = 'Uploaded file must have a filename'


class FileTooLargeException(TaskTemplateException):
    """Exception raised when an uploaded file is too large."""

    status_code: int = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    detail: str = 'Uploaded file is too large'

    def __init__(self, size: int | None = None, max_size: int | None = None):
        if size and max_size:
            self.detail = f'Uploaded file is too large (size: {size} bytes, max size: {max_size} bytes)'
        super().__init__(detail=self.detail)
