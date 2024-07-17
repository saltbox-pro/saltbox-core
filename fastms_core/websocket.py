from __future__ import annotations

import logging

from collections.abc import Awaitable
from typing import Annotated, Callable, TypeVar

from fastapi import Depends, WebSocket, WebSocketDisconnect

LOGGER = logging.getLogger(__name__)

T = TypeVar('T')


class WebSocketHandler:
    """ Socket wrapper handles connection and disconnection """

    def __init__(self, websocket: WebSocket) -> None:
        self.websocket = websocket

    async def start(self) -> None:
        await self.websocket.accept()

    @classmethod
    async def create(cls, websocket: WebSocket) -> 'WebSocketHandler':
        obj = cls(websocket)
        await obj.start()
        return obj

    @staticmethod
    def swallow_disconnection(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T | None]]:
        async def wrapper(self: 'WebSocketHandler', *args, **kwargs) -> T | None:
            try:
                return await func(self, *args, **kwargs)
            except WebSocketDisconnect:
                client = self.websocket.client
                if not client:
                    LOGGER.info('/ws_jobs websocket has been disconnected')
                else:
                    LOGGER.info(
                        '/ws_jobs websocket for %s:%i has been disconnected',
                        client.host,
                        client.port)
                return None
        return wrapper

    @swallow_disconnection
    async def send_text(self, data: str) -> None:
        await self.websocket.send_text(data)


async def get_websocket_handler(websocket: WebSocket) -> WebSocketHandler:
    return await WebSocketHandler.create(websocket)


WebSocketHandlerDependency = Annotated[WebSocketHandler, Depends(get_websocket_handler)]
