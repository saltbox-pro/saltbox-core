from fastapi import status

from saltbox_core.exceptions import CoreException


class MinionCollectionException(CoreException):
    """Base exception for Minion Collection errors."""

    detail: str = 'An error occurred in the Minion Collection service.'


class PiplineBuilderException(MinionCollectionException):
    """Exception raised for errors in the MongoDB pipeline builder."""

    detail: str = 'An error occurred while building the MongoDB aggregation pipeline.'


class UnsupportedFieldTypeException(MinionCollectionException):
    """Exception raised for unsupported field types in the MongoDB pipeline builder."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    detail: str = 'The specified field type is not supported for aggregation.'
