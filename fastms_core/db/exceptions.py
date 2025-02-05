class RepositoryError(Exception): ...


class ObjectNotFoundError(RepositoryError):
    def __init__(self, detail: str = 'Object not found') -> None:
        self.detail = detail
        super().__init__(self.detail)


class MultipleObjectsFoundError(RepositoryError): ...


class DuplicateKeyError(RepositoryError):
    def __init__(self, detail: str = 'Duplicate key error') -> None:
        self.detail = detail
        super().__init__(self.detail)


class ObjCreationError(RepositoryError): ...


class ObjUpdateError(RepositoryError): ...


class MultipleObjectsReturnError(RepositoryError): ...


class ObjectCreateError(RepositoryError):
    def __init__(self, detail: str = 'Object not created') -> None:
        self.detail = detail
        super().__init__(self.detail)


class ObjectUpdateError(RepositoryError):
    def __init__(self, detail: str = 'Object not updated') -> None:
        self.detail = detail
        super().__init__(self.detail)


class PiplineBuilderError(RepositoryError): ...
