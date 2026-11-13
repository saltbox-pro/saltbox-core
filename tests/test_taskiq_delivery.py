import asyncio
from unittest.mock import AsyncMock

import pytest

from saltbox_sdk.utilities.taskiq_delivery import defer_task_delivery


class DeliveryStub:
    def __init__(self, ack: AsyncMock) -> None:
        self.ack_mock = ack
        self.reject_mock = AsyncMock()

    async def ack(self) -> None:
        await self.ack_mock()

    async def reject(self, requeue: bool = False) -> None:
        await self.reject_mock(requeue=requeue)


@pytest.mark.asyncio
async def test_deferred_publication_precedes_acknowledgement() -> None:
    calls: list[str] = []

    async def publish() -> None:
        calls.append('publish-confirmed')

    async def ack() -> None:
        calls.append('ack')

    delivery = DeliveryStub(AsyncMock(side_effect=ack))
    await defer_task_delivery(delivery, publish)
    assert calls == ['publish-confirmed', 'ack']
    delivery.reject_mock.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('error', [ConnectionError('publish failed'), asyncio.CancelledError()])
async def test_failed_or_cancelled_publication_returns_original(error: BaseException) -> None:
    delivery = DeliveryStub(AsyncMock())
    publish = AsyncMock(side_effect=error)
    with pytest.raises(type(error)):
        await defer_task_delivery(delivery, publish)
    delivery.ack_mock.assert_not_awaited()
    delivery.reject_mock.assert_awaited_once_with(requeue=True)


@pytest.mark.asyncio
async def test_lost_ack_does_not_publish_another_copy() -> None:
    delivery = DeliveryStub(AsyncMock(side_effect=ConnectionError('ack failed')))
    publish = AsyncMock()
    with pytest.raises(ConnectionError, match='ack failed'):
        await defer_task_delivery(delivery, publish)
    publish.assert_awaited_once()
    delivery.reject_mock.assert_not_awaited()
