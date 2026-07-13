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


class InvalidParentCollectionException(MinionCollectionException):
    """Exception raised when attempting to set a collection's parent to itself or one of its children."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    detail: str = 'Cannot set parent_slug to self or any of its children.'
