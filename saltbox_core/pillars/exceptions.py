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


class PillarTargetIdRequiredException(PillarException):
    """Exception raised when attempting to create a MINION or COLLECTION pillar without tgt_id."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    detail: str = 'tgt_id is required for MINION and COLLECTION pillar types.'


class PillarTgtNotFoundException(PillarException):
    """Exception raised when the specified tgt_id does not exist for MINION or COLLECTION pillar types."""

    status_code: int = status.HTTP_404_NOT_FOUND
    detail: str = 'The specified tgt_id does not exist.'


class PillarUpdateSecretNotAllowedException(PillarException):
    """Exception raised when attempting to update a  secret pillar."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    detail: str = 'Updating secret pillars is not allowed.'


class PillarTgtTypeInvalidException(PillarException):
    """Exception raised when attempting to create a pillar with an invalid tgt_type."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    detail: str = 'Invalid tgt_type specified for pillar.'


class PillarEncryptionKeyNotConfiguredException(PillarException):
    """Exception raised when core is asked to encrypt/decrypt a secret pillar but no key is configured."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    detail: str = 'Pillars encryption key is not configured on core.'


class PillarCryptoException(PillarException):
    """Exception raised on pillar crypto errors (invalid payload, decrypt failure, etc)."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    detail: str = 'Pillars cryptographic operation failed.'


class PillarInvalidEncryptionPayloadException(PillarCryptoException):
    """Exception raised when trying to decrypt a pillar with invalid $enc payload structure."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    detail: str = 'Invalid encryption payload structure.'
