from fastapi import status

from saltbox_core.exceptions import CoreException


class MasterServiceException(CoreException):
    """Base exception for MasterService."""

    detail: str = 'MasterService error occurred'


class UnknownUserException(MasterServiceException):
    """Exception raised when an unknown user is specified."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    detail: str = 'Unknown user specified'


class TimeoutResponseToMasterException(MasterServiceException):
    """Exception raised when a timeout occurs while waiting for a response from a master."""

    status_code: int = status.HTTP_504_GATEWAY_TIMEOUT
    detail: str = 'Execution is too long, try lesser count of load size or wait master to boot'
