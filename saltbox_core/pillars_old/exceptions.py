from fastapi import status

from saltbox_core.exceptions import CoreException


class PillarServiceException(CoreException):
    """Base exception for PillarService."""

    detail: str = 'An error occurred in the PillarService'
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR


class PillarServiceParseCsvException(PillarServiceException):
    """Custom exception for errors during CSV parsing in PillarService."""

    detail: str = 'An error occurred while parsing the CSV file'
    status_code: int = status.HTTP_400_BAD_REQUEST
