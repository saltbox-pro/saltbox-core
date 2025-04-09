class RepositoryError(Exception): ...


class ObjectNotFoundError(RepositoryError):
    def __init__(
        self, detail: str = 'Object not found', obj_type: str | None = None, query: dict | None = None
    ) -> None:
        self.detail = detail if detail else 'Object not found'

        if obj_type:
            self.detail += f' - {obj_type}'

        if query:
            self.detail += f' - {query!s}'

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


class PipelineBuilderError(RepositoryError): ...
