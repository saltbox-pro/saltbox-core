import contextlib
from collections.abc import Generator


@contextlib.contextmanager
def replace_raised(rerise: type[BaseException], *catch: type[BaseException], keep_trace: bool = True) -> Generator:
    """
    Re-rise exceptions raised inside the context manager as a specified type
    """
    try:
        yield
    except catch as err:
        if keep_trace:
            raise rerise(err) from err
        else:
            raise rerise(err) from None
