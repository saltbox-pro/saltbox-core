from __future__ import annotations

import logging

from contextlib import AbstractContextManager
from typing import Type
from types import TracebackType

from fastapi import WebSocket, WebSocketDisconnect

LOGGER = logging.getLogger(__name__)


class IsSocketDisconnected(AbstractContextManager):
    """
    Supress WebSocketDisconnect error
    """
    def __init__(self, websocket: WebSocket) -> None:
        self.websocket = websocket
        self.is_excepted = False

    def __enter__(self) -> 'IsSocketDisconnected':
        return self

    def __exit__(
        self,
        exttype: Type[BaseException] | None,
        extint: BaseException | None,
        exttb: TracebackType | None,
    ) -> bool:
        if exttype is None:
            return True
        if issubclass(exttype, WebSocketDisconnect):
            self.is_excepted = True
            client = self.websocket.client
            if not client:
                LOGGER.info('/ws_jobs websocket has been disconnected')
            else:
                LOGGER.info(
                    '/ws_jobs websocket for %s:%i has been disconnected',
                    client.host,
                    client.port)
            return True
        return False

    def __bool__(self):
        return self.is_excepted
