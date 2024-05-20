#!/usr/bin/env python3
import asyncio
import signal


async def main():
    futures = []

    futures.append(await asyncio.create_subprocess_exec('salt-api'))
    futures.append(await asyncio.create_subprocess_exec('salt-master'))

    await asyncio.gather(*[future.communicate() for future in futures])


if __name__ == '__main__':
    loop = asyncio.new_event_loop()
    for signame in {'SIGINT', 'SIGTERM'}:
        loop.add_signal_handler(getattr(signal, signame), loop.stop)

    try:
        loop.run_until_complete(main())
    finally:
        loop.close()
