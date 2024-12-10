import asyncio
import datetime
import json
import logging.config
from contextlib import AbstractContextManager
from types import TracebackType

from fastapi import WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState
from jwt import InvalidTokenError
from pydantic import BaseModel, ValidationError
from redis.asyncio import Redis
from redis.asyncio.client import PubSub

from fastms_core.config import LOG_CONFIG
from fastms_core.dependencies import decode_jwt

logging.config.dictConfig(LOG_CONFIG.model_dump())

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
        self._token_refresher_task: asyncio.Task | None = None

    async def _check_connection(self) -> None:
        if (
            self.websocket.application_state == WebSocketState.DISCONNECTED
            or self.websocket.client_state == WebSocketState.DISCONNECTED
        ):
            LOGGER.debug('WebSocket disconnected')
            raise WebSocketDisconnect
        if self.token_expiration and datetime.datetime.now(datetime.UTC) >= self.token_expiration:
            LOGGER.debug('Token expired: %s', self.token_expiration)
            await self.close('Token expired')
            raise WebSocketDisconnect

    async def _obtain_token_msg(self) -> None:
        await self._check_connection()
        message = await self.websocket.receive_text()
        await self._process_token_message(message)

    async def _process_token_message(self, token: str) -> None:
        try:
            payload = await decode_jwt(token)
            self.token_expiration = datetime.datetime.fromtimestamp(payload['exp'], datetime.UTC)
        except (InvalidTokenError, ValidationError, IndexError) as e:
            LOGGER.error('Error processing token message %s', e)
            await self.close(f'Invalid token message: {e!s}')

    async def _close_websocket(self, reason: str) -> None:
        await self.websocket.close(code=1008, reason=reason)

    async def accept(self) -> None:
        await self.websocket.accept()
        await self._obtain_token_msg()

        self._token_refresher_task = asyncio.create_task(self._token_refresher())

    async def send(self, message: str) -> None:
        await self._check_connection()
        await self.websocket.send_text(message)

    async def _token_refresher(self) -> None:
        while True:
            try:
                await self._obtain_token_msg()
            except WebSocketDisconnect:
                break

    async def close(self, msg: str) -> None:
        if self._token_refresher_task:
            self._token_refresher_task.cancel()
            try:
                await self._token_refresher_task
            except asyncio.CancelledError:
                pass
        await self._close_websocket(msg)


class PubSubAuthenticatedWebSocket(AuthenticatedWebSocket):
    """WebSocket connection for PubSub messages forwarding

    Example:
    @router.websocket('/pubsub')
    async def pubsub_endpoint(websocket: WebSocket, rdb: RedisDependency) -> None:
        secure_websocket = PubSubAuthenticatedWebSocket(websocket)
        await secure_websocket.accept()

        async with rdb.pubsub() as pubsub:
            await pubsub.psubscribe(f'job:{jid}:return')
            await secure_websocket.pubsub_forwarder(pubsub, schema=JobResult)
        # or just:
        # await secure_websocket.handle_pubsub(channel='job:*:new', schema=Job)
    """

    def __init__(self, websocket: WebSocket, rdb: Redis | None = None) -> None:
        super().__init__(websocket)
        self.rdb = rdb

    async def _process_pubsub_message(self, message: dict, schema: type[BaseModel]) -> None:
        data_str = message['data'].decode()
        try:
            data = json.loads(data_str)
            instance = schema(**data)
            await self.send(instance.model_dump_json(by_alias=True))
        except (ValidationError, TypeError, json.JSONDecodeError) as e:
            LOGGER.error('Error processing pubsub message %s', e)

    async def pubsub_forwarder(self, pubsub: PubSub, schema: type[BaseModel]) -> None:
        async for message in pubsub.listen():
            if message['type'] not in PubSub.PUBLISH_MESSAGE_TYPES:
                continue
            try:
                await self._process_pubsub_message(message, schema)
            except WebSocketDisconnect:
                break

    async def handle_pubsub(self, channel: str, schema: type[BaseModel]) -> None:
        if self.rdb is None:
            LOGGER.error('No Redis connection')
            await self.close('No Redis connection')
            return
        async with self.rdb.pubsub() as pubsub:
            await pubsub.psubscribe(channel)
            await self.pubsub_forwarder(pubsub, schema)
