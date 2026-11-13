from unittest.mock import AsyncMock, Mock, patch

import pytest
from pamqp.commands import Basic
from taskiq import BrokerMessage, TaskiqMessage
from taskiq.exceptions import NoResultError

from saltbox_sdk.utilities.taskiq import UniqueIdMiddleware
from saltbox_sdk.utilities.taskiq_rabbit import SaltboxAioPikaBroker


def message(queue: str = 'queue-notify') -> BrokerMessage:
    return BrokerMessage(
        task_id='test-id', task_name='notify', message=b'payload', labels={'queue_name': queue, 'delay': '1'}
    )


def broker_with_channel(confirmation: object) -> tuple[SaltboxAioPikaBroker, Mock]:
    broker = SaltboxAioPikaBroker()
    channel = Mock(
        publisher_confirms=True,
        declare_queue=AsyncMock(return_value=Mock(name='delay-queue')),
        default_exchange=Mock(publish=AsyncMock(return_value=confirmation)),
    )
    broker.write_channel = channel
    return broker, channel


@pytest.mark.asyncio
@pytest.mark.parametrize('queue', ['queue-notify', 'queue-default', 'queue-salt'])
async def test_delay_returns_to_requested_queue(queue: str) -> None:
    broker, channel = broker_with_channel(Basic.Ack())
    await broker.kick(message(queue))
    declaration = channel.declare_queue.call_args.kwargs
    assert declaration['arguments']['x-dead-letter-routing-key'] == queue
    assert declaration['arguments']['x-dead-letter-strategy'] == 'at-least-once'
    assert declaration['arguments']['x-overflow'] == 'reject-publish'
    assert declaration['arguments']['x-queue-type'] == 'quorum'
    publication = channel.default_exchange.publish.call_args
    assert publication.kwargs['routing_key'] == channel.declare_queue.return_value.name
    assert publication.kwargs['mandatory'] is True
    assert publication.args[0].body == b'payload'


@pytest.mark.asyncio
@pytest.mark.parametrize('confirmation', [None, Basic.Nack(), Basic.Reject()])
async def test_missing_confirmation_is_failure(confirmation: object) -> None:
    broker, _ = broker_with_channel(confirmation)
    with pytest.raises(RuntimeError, match='not acknowledged'):
        await broker.kick(message())


@pytest.mark.asyncio
async def test_regular_publication_uses_original_broker() -> None:
    broker = SaltboxAioPikaBroker()
    outgoing = message()
    outgoing.labels.pop('delay')
    with patch('taskiq_aio_pika.AioPikaBroker.kick', new_callable=AsyncMock) as kick:
        await broker.kick(outgoing)
        kick.assert_awaited_once_with(outgoing)


@pytest.mark.asyncio
@pytest.mark.parametrize('publish_fails', [False, True])
async def test_busy_task_is_deferred_without_normal_retry(publish_fails: bool) -> None:
    middleware = UniqueIdMiddleware(rdb=Mock())
    broker = SaltboxAioPikaBroker().with_middlewares(middleware)
    incoming = Mock(ack=AsyncMock(), reject=AsyncMock())
    broker._deliveries['delivery'] = incoming
    task = TaskiqMessage(
        task_id='id', task_name='notify', args=[], kwargs={},
        labels={broker.DELIVERY_LABEL: 'delivery', 'queue_name': 'queue-notify'},
    )
    error = ConnectionError('publish failed') if publish_fails else None
    with (
        patch.object(middleware, 'acquire_execution', new_callable=AsyncMock, return_value=False),
        patch.object(broker, 'kick', new_callable=AsyncMock, side_effect=error) as kick,
        pytest.raises(NoResultError),
    ):
        await broker.acquire_unique_task(task)
    successor = broker.formatter.loads(kick.call_args.args[0].message)
    assert successor.labels['queue_name'] == 'queue-notify'
    assert successor.labels['delay'] == '1'
    assert middleware.DEFERRED_LABEL not in successor.labels
    assert task.labels[middleware.DEFERRED_LABEL]
    assert '_retries' not in successor.labels
    if publish_fails:
        incoming.reject.assert_awaited_once_with(requeue=True)
        incoming.ack.assert_not_awaited()
    else:
        incoming.ack.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_return_cannot_fall_through_to_automatic_ack() -> None:
    broker = SaltboxAioPikaBroker()
    incoming = Mock(processed=False, ack=AsyncMock())
    broker._deliveries['delivery'] = incoming
    broker._blocked_acks.add('delivery')
    await broker._ack_callback('delivery', incoming)()
    incoming.ack.assert_not_awaited()
