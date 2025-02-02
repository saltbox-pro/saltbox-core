import asyncio
import datetime
import functools
import json
import logging.config
from collections.abc import Callable
from contextlib import AbstractContextManager
from inspect import isclass
from types import TracebackType
from typing import Any, TypedDict

from fastapi import WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState
from jwt import InvalidTokenError, PyJWKClientError
from pydantic import BaseModel, ValidationError
from redis.asyncio import Redis
from redis.asyncio.client import PubSub

from fastms_core.config import LOG_CONFIG
from fastms_core.dependencies import decode_jwt

logging.config.dictConfig(LOG_CONFIG.model_dump())

LOGGER = logging.getLogger(__name__)


class RedisPubSubMessage(TypedDict):
    type: str
    pattern: str | None
    channel: str
    data: bytes


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
        exttype: type[BaseException] | None,
        extint: BaseException | None,
        exttb: TracebackType | None,
    ) -> bool:
        if exttype is None:
            return True
        if issubclass(exttype, WebSocketDisconnect):
            self.is_excepted = True
            client = self.websocket.client
            if not client:
                LOGGER.debug('/ws_jobs websocket has been disconnected')
            else:
                LOGGER.debug(
                    '/ws_jobs websocket for %s:%i has been disconnected',
                    client.host,
                    client.port,
                )
            return True
        return False

    def __bool__(self) -> bool:
        return self.is_excepted


def _check_ws_connection(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator to check secure WebSocket connection state
    Raises WebSocketDisconnect if token expired or WebSocket disconnected
    """

    @functools.wraps(fn)
    async def wrapper(self: 'AuthenticatedWebSocket', *args: tuple, **kwargs: dict) -> Any:
        if self._already_closed:
            raise WebSocketDisconnect
        if self.token_expiration and datetime.datetime.now(datetime.UTC) >= self.token_expiration:
            LOGGER.debug('Token expired: %s', self.token_expiration)
            await self.close('Token expired')
            raise WebSocketDisconnect
        return await fn(self, *args, **kwargs)

    return wrapper


class AuthenticatedWebSocket:
    """Base class for authenticated WebSocket connections

    Example:
    @router.websocket('')
    async def ws_endpoint(websocket: WebSocket) -> None:
        secure_websocket = AuthenticatedWebSocket(websocket)
        await secure_websocket.accept()
        logger.info('Start sending messages')

        while True:
            try:
                await secure_websocket.send('Hello')
                await asyncio.sleep(3)
            except WebSocketDisconnect:
                break
    """

    def __init__(self, websocket: WebSocket) -> None:
        self.websocket = websocket
        self.token_expiration: datetime.datetime | None = None
        self._subtasks: set[asyncio.Task] = set()

    @property
    def _already_closed(self) -> bool:
        LOGGER.debug('Server state: %s', self.websocket.application_state)
        LOGGER.debug('Client state: %s', self.websocket.client_state)
        return (
            self.websocket.application_state == WebSocketState.DISCONNECTED
            or self.websocket.client_state == WebSocketState.DISCONNECTED
        )

    @_check_ws_connection
    async def _obtain_token_msg(self) -> None:
        LOGGER.debug('Await token message')
        message = await self.websocket.receive_text()
        await self._process_token_message(message)

    async def _process_token_message(self, token: str) -> None:
        LOGGER.debug('Processing token message')
        try:
            payload = await decode_jwt(token)
            self.token_expiration = datetime.datetime.fromtimestamp(payload['exp'], datetime.UTC)
        except (InvalidTokenError, ValidationError, IndexError, PyJWKClientError) as e:
            LOGGER.error('Error processing token message %s', e)
            await self.close(f'Invalid token message: {e!s}')

    async def accept(self) -> None:
        try:
            await self.websocket.accept()
            await self._obtain_token_msg()
        except WebSocketDisconnect:
            await self.close('WebSocket disconnected')

        self._subtasks.add(asyncio.create_task(self._token_refresher_task_manager()))

    async def _token_refresher_task_manager(self) -> None:
        while not self._already_closed:
            LOGGER.debug('Start token refresher task')
            token_refresher_task = asyncio.create_task(self._token_refresher())
            self._subtasks.add(token_refresher_task)
            try:
                LOGGER.debug('Await token refresher task')
                await token_refresher_task
            except WebSocketDisconnect:
                await self.close('WebSocket disconnected')
            except Exception as e:
                LOGGER.error('Error in _token_refresher_task: %s', e)
            finally:
                self._subtasks.remove(token_refresher_task)
                token_refresher_task.cancel()
                LOGGER.debug('Token_refresher_task cancelled')
                await asyncio.sleep(1)

    @_check_ws_connection
    async def send_text(self, message: str) -> None:
        await self.websocket.send_text(message)

    async def _token_refresher(self) -> None:
        while not self._already_closed:
            await self._obtain_token_msg()

    async def close(self, msg: str) -> None:
        LOGGER.debug('Cancel all subtasks: %s', self._subtasks)
        for task in self._subtasks:
            task.cancel()

        if not self._already_closed:
            await self.websocket.close(code=1008, reason=msg)


class PubSubAuthenticatedWebSocket(AuthenticatedWebSocket):
    """WebSocket connection for PubSub messages forwarding

    Example:
    @ws_router.websocket('/pubsub')
    async def channel_forwarder(websocket: WebSocket, rdb: RedisDependency) -> None:
        secure_websocket = PubSubAuthenticatedWebSocket(websocket, rdb)

        await secure_websocket.handle_pubsub({'job:*:new': Job, 'channel2': AnotherModel})
    """

    def __init__(self, websocket: WebSocket, rdb: Redis) -> None:
        super().__init__(websocket)
        self._rdb = rdb

    async def _process_channel_message(self, message: RedisPubSubMessage, schema: type[BaseModel]) -> None:
        data_str = message['data'].decode()
        try:
            data = json.loads(data_str)
            instance = schema(**data)
            await self.send_text(instance.model_dump_json(by_alias=True))
        except (ValidationError, TypeError, json.JSONDecodeError) as e:
            LOGGER.error('Error processing pubsub message %s', e)

    async def _process_channel_message_by_callback(self, message: RedisPubSubMessage, callback: Callable) -> None:
        data_str = message['data'].decode()
        try:
            data = json.loads(data_str)
            result = callback(data=data)

            if result is not None:
                if isinstance(result, str):
                    await self.send_text(result)
                else:
                    await self.send_text(json.dumps(result))
        except (ValidationError, TypeError, json.JSONDecodeError) as e:
            LOGGER.error('Error processing pubsub message %s', e)

    async def _message_forwarder(self, channel: str, handler: type[BaseModel] | Callable) -> None:
        async with self._rdb.pubsub() as pubsub:
            await pubsub.psubscribe(channel)
            async for message in pubsub.listen():
                if self._already_closed:
                    LOGGER.debug('Cant forward msg - Websocket already closed')
                    break
                if message['type'] not in PubSub.PUBLISH_MESSAGE_TYPES:
                    continue

                if isclass(handler) and issubclass(handler, BaseModel):
                    await self._process_channel_message(message, handler)
                elif callable(handler):
                    await self._process_channel_message_by_callback(message, handler)

                msg = 'Unsupported handler type'
                raise Exception(msg)

        LOGGER.debug('Exit from _message_forwarder')

    async def handle_pubsub(self, channel_schema_map: dict[str, type[BaseModel] | Callable]) -> None:
        await self.accept()
        channel_tasks = []
        for channel, handler in channel_schema_map.items():
            task = asyncio.create_task(self._message_forwarder(channel, handler))
            channel_tasks.append(task)
            self._subtasks.add(task)

        try:
            await asyncio.gather(*channel_tasks)
        except WebSocketDisconnect:
            LOGGER.debug('Close in handle_pubsub')
            await self.close('WebSocket disconnected')
        except asyncio.CancelledError:
            LOGGER.debug('Catch asyncio.CancelledError in handle_pubsub')
