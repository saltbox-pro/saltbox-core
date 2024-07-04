from __future__ import annotations

from typing import Any, Tuple


def fill_salt_kwarg_from_arg(
    arg: None | list[Any], kwarg: None | dict[str, Any]
) -> Tuple[None | list[Any], None | dict[str, Any]]:
    """
    Extract kwarg dicts from args for SaltStack messages

    SaltStack has *args, **kwargs ideom, but often puts kwargs in args list as
    an object with the special `__kwarg__: True` key. Function make "canonical"
    args and kwargs.

    :param arg: list of args e.g. from job/*/ret message
    :param kwarg: dict of kwargs e.g. from job/*/ret message
    :return: updated list of args and dict of kwargs
    """
    def is_kwargs(val: Any) -> bool:
        return isinstance(val, dict) and '__kwarg__' in val

    if not arg or not (extracted_kwargs := list(filter(is_kwargs, arg))):
        return arg, kwarg

    new_arg = list(filter(lambda val: not is_kwargs(val), arg))

    new_kwarg = {}
    if kwarg:
        new_kwarg.update(kwarg)

    for kwarg_dict in extracted_kwargs:
        kwarg_dict.pop('__kwarg__')
        new_kwarg.update(kwarg_dict)

    return new_arg, new_kwarg
