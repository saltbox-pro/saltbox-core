class RepositoryError(Exception): ...


class ObjectNotFoundError(RepositoryError):
    def __init__(self, detail: str = 'Object not found') -> None:
        self.detail = detail
        super().__init__(self.detail)


class MultipleObjectsFoundError(RepositoryError):
    def __init__(self, detail: str = 'Multiple objects found') -> None:
        self.detail = detail
        super().__init__(self.detail)


class DuplicateKeyError(RepositoryError):
    def __init__(self, detail: str = 'Duplicate key error') -> None:
        self.detail = detail
        super().__init__(self.detail)


class ObjectCreateError(RepositoryError):
    def __init__(self, detail: str = 'Object not created') -> None:
        self.detail = detail
        super().__init__(self.detail)


class ObjectUpdateError(RepositoryError):
    def __init__(self, detail: str = 'Object not updated') -> None:
        self.detail = detail
        super().__init__(self.detail)
