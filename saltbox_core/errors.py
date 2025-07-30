from fastapi import status


class CoreError(Exception):
    """Base class for all core-related exceptions."""

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    detail: str = 'An unexpected error occurred in the core service.'

    def __str__(self) -> str:
        return f'{self.__class__.__name__}: {self.detail}'
