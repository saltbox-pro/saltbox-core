import logging
from typing import Any

logger = logging.getLogger(__name__)


def solve_path(path: list[str | int], obj: object) -> Any:
    current = obj
    for key in path:
        try:
            if hasattr(current, '__getitem__'):
                current = current[key]
            else:
                current = getattr(current, key)  # type: ignore[arg-type]
        except (IndexError, KeyError, TypeError, AttributeError) as err:
            path_repr = []
            for i in path:
                path_repr.append(f'[{i}]' if isinstance(i, int) else i)
            logger.error('Failed to follow path "%s" on "%s"', '.'.join(path_repr), key)
            raise ValueError(err) from err
    return current
