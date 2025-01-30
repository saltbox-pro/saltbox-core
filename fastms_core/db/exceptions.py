class RepositoryError(Exception):
    ...


class ObjectNotFoundError(RepositoryError):
    ...


class MultipleObjectsFoundError(RepositoryError):
    ...


class ObjUniqueError(RepositoryError):
    ...


class ObjCreationError(RepositoryError):
    ...


class ObjUpdateError(RepositoryError):
    ...
