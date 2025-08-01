from fastapi import status

from saltbox_core.exceptions import CoreException


class CryptError(CoreException):
    """Base exception for cryptographic operations."""

    detail: str = 'Cryptographic operation error occurred'


class CreateSignError(CryptError):
    """Exception raised when creating a signature fails."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    detail: str = 'Failed to create signature'


class VerifySignError(CryptError):
    """Exception raised when verifying a signature fails."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    detail: str = 'Failed to verify signature'
