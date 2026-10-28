import asyncio
import signal
from collections.abc import Callable, Coroutine
from typing import Any


def run_until_sigterm(async_main: Callable[[], Coroutine[Any, Any, None]]) -> None:
    async def run() -> None:
        task = asyncio.current_task()
        if task is not None:
            asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, task.cancel)

        await async_main()

    try:
        asyncio.run(run())
    except asyncio.CancelledError:
        pass
