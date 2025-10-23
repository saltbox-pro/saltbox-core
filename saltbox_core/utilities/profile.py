import logging
import time
from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar

logger = logging.getLogger(__name__)


def humanize_time(seconds: float) -> str:
    if seconds < 1:
        return f'{seconds * 1000:.2f} ms'
    mins, sec = divmod(seconds, 60)
    return f'{int(mins)}m {sec:.2f}s'


P = ParamSpec('P')
R = TypeVar('R')


def log_duration(label: str | None = None, log_level: int = logging.INFO) -> Callable[[Callable[P, R]], Callable[P, R]]:
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                elapsed = time.perf_counter() - start
                name = label or f'{func.__qualname__}()'
                logger.log(log_level, '%s duration: %s', name, humanize_time(elapsed))
        return wrapper
    return decorator
