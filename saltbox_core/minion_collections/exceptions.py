from fastapi import status

from saltbox_core.exceptions import CoreException


class MinionCollectionException(CoreException):
    """Base exception for Minion Collection errors."""

    detail: str = 'An error occurred in the Minion Collection service.'


class InvalidParentCollectionException(MinionCollectionException):
    """Exception raised when attempting to set a collection's parent to itself or one of its children."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    detail: str = 'Cannot set parent_slug to self or any of its children.'


class DuplicateChildCollectionTitleException(MinionCollectionException):
    """Exception raised when a collection title duplicates one of the new parent's direct children."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    detail: str = 'Collection title must be unique among the direct children of the parent collection.'


class UnknownCollectionReferenceException(MinionCollectionException):
    """Exception raised when a collection query references collections that do not exist."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    detail: str = 'Collection query references unknown collections.'

    def __init__(self, slugs: list[str]) -> None:
        self.slugs = slugs
        super().__init__(f'Collection query references unknown collections: {", ".join(slugs)}')


class CyclicCollectionReferenceException(MinionCollectionException):
    """Exception raised when collection references and parents form a cycle."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    detail: str = 'Collection references form a cycle.'

    def __init__(self, slugs: list[str]) -> None:
        self.slugs = slugs
        super().__init__(f'Collection references form a cycle: {" -> ".join(slugs)}')


class ReferencedCollectionDeleteException(MinionCollectionException):
    """Exception raised when deleting collections that are referenced by other collections."""

    status_code: int = status.HTTP_409_CONFLICT
    detail: str = 'Collection is referenced by other collections.'

    def __init__(self, slugs: list[str]) -> None:
        self.slugs = slugs
        super().__init__(f'Collection is referenced by other collections: {", ".join(slugs)}')
