class TaskException(Exception):
    ...


class TaskDoesNotExistException(TaskException):
    ...


class TaskServieException(TaskException):
    ...


class TaskTemplateException(Exception):
    ...


class TaskTemplateDoesNotExistException(TaskTemplateException):
    ...


class TaskTemplateServieException(TaskTemplateException):
    ...
