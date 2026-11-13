from unittest.mock import AsyncMock, Mock, patch

import pytest
from taskiq import InMemoryBroker, TaskiqMessage, TaskiqResult

from saltbox_sdk.utilities.taskiq import SmartRetryMiddleware, TaskAlreadyRunningException, UniqueIdMiddleware


@pytest.mark.parametrize(
    ('first', 'second'),
    [
        ({'a': 'x__y', 'b': 'z'}, {'a': 'x', 'b': 'y__z'}),
        ({'a': 1, 'b': None}, {'a': '1', 'b': None}),
    ],
)
def test_unique_keys_do_not_collide(first: dict[str, str | int | None], second: dict[str, str | int | None]) -> None:
    middleware = UniqueIdMiddleware(rdb=Mock())
    assert middleware.get_task_lock_key('task', ['a', 'b'], first) != middleware.get_task_lock_key(
        'task', ['a', 'b'], second
    )


def test_unique_key_is_independent_of_dictionary_order() -> None:
    middleware = UniqueIdMiddleware(rdb=Mock())
    first = {'item': {'a': 1, 'b': 2}, 'mode': 'update'}
    second = {'mode': 'update', 'item': {'b': 2, 'a': 1}}
    assert middleware.get_task_lock_key('task', ['item', 'mode'], first) == middleware.get_task_lock_key(
        'task', ['mode', 'item'], second
    )


def test_missing_unique_argument_is_not_none() -> None:
    middleware = UniqueIdMiddleware(rdb=Mock())
    with pytest.raises(ValueError, match='item'):
        middleware.get_task_lock_key('task', ['item'], {})
    assert middleware.get_task_lock_key('task', ['item'], {'item': None})


def test_unique_key_includes_argument_names_and_task_name() -> None:
    middleware = UniqueIdMiddleware(rdb=Mock())
    key = middleware.get_task_lock_key('task', ['item'], {'item': 'x'})
    assert key != middleware.get_task_lock_key('task', ['other'], {'other': 'x'})
    assert key != middleware.get_task_lock_key('other-task', ['item'], {'item': 'x'})


def make_message() -> TaskiqMessage:
    return TaskiqMessage(
        task_id='test-id',
        task_name='test-task',
        labels={'unique_kwargs': "['item']", 'unique_lock_timeout': '120'},
        args=[],
        kwargs={'item': 'document'},
    )


def test_positional_arguments_and_defaults_share_key() -> None:
    middleware = UniqueIdMiddleware(rdb=Mock())
    broker = InMemoryBroker().with_middlewares(middleware)

    @broker.task(task_name='test-task')
    async def task(item: str, mode: str = 'update') -> None:
        pass

    positional = make_message()
    positional.args = ['document']
    positional.kwargs = {}
    keyword = make_message()
    keyword.kwargs['mode'] = 'update'
    assert middleware.get_task_arguments(positional) == middleware.get_task_arguments(keyword)


@pytest.mark.asyncio
async def test_reservation_sets_timeout_on_actual_key() -> None:
    redis = Mock(set=AsyncMock(return_value=True))
    middleware = UniqueIdMiddleware(rdb=redis)
    message = await middleware.pre_send(make_message())
    redis.set.assert_awaited_once_with(
        message.labels[middleware.LOCK_KEY_LABEL], message.labels[middleware.OWNER_LABEL], nx=True, ex=120
    )


@pytest.mark.asyncio
async def test_busy_key_rejects_duplicate() -> None:
    middleware = UniqueIdMiddleware(rdb=Mock(set=AsyncMock(return_value=None)))
    message = make_message()
    with pytest.raises(TaskAlreadyRunningException):
        await middleware.pre_send(message)
    assert middleware.OWNER_LABEL not in message.labels


@pytest.mark.asyncio
async def test_completion_uses_original_reservation_after_argument_change() -> None:
    redis = Mock(set=AsyncMock(return_value=True), eval=AsyncMock(return_value=1))
    middleware = UniqueIdMiddleware(rdb=redis)
    message = await middleware.pre_send(make_message())
    key = message.labels[middleware.LOCK_KEY_LABEL]
    owner = message.labels[middleware.OWNER_LABEL]
    message.kwargs['item'] = 'changed-during-execution'
    await middleware.post_execute(message, TaskiqResult(is_err=False, return_value=None, execution_time=0))
    redis.eval.assert_awaited_once()
    assert redis.eval.call_args.args[1:] == (2, key, f'{key}:execution', owner, '')


@pytest.mark.asyncio
async def test_release_enqueue_does_not_release_execution() -> None:
    redis = Mock(set=AsyncMock(return_value=True), eval=AsyncMock(return_value=1))
    middleware = UniqueIdMiddleware(rdb=redis)
    message = await middleware.pre_send(make_message())
    message.labels[middleware.EXECUTION_OWNER_LABEL] = 'execution-token'
    lock = middleware.get_lock(message)
    assert lock is not None
    await lock.release_enqueue_lock()
    assert redis.eval.call_args.args[1:] == (1, lock.enqueue_key, lock.enqueue_owner)


@pytest.mark.asyncio
async def test_lock_handle_retains_owner_when_message_labels_change() -> None:
    redis = Mock(set=AsyncMock(return_value=True), eval=AsyncMock(return_value=0))
    middleware = UniqueIdMiddleware(rdb=redis)
    message = await middleware.pre_send(make_message())
    message.labels[middleware.EXECUTION_OWNER_LABEL] = 'old-execution'
    lock = middleware.get_lock(message)
    assert lock is not None
    message.labels[middleware.OWNER_LABEL] = 'new-enqueue'
    message.labels[middleware.EXECUTION_OWNER_LABEL] = 'new-execution'
    await lock.release_all_locks()
    await lock.release_all_locks()
    assert redis.eval.await_count == 2
    assert redis.eval.call_args.args[1:] == (
        2, lock.enqueue_key, lock.execution_key, lock.enqueue_owner, 'old-execution'
    )


@pytest.mark.asyncio
@pytest.mark.parametrize('lock_timeout', ['0', '-1', 'invalid'])
async def test_invalid_timeout_does_not_reserve(lock_timeout: str) -> None:
    redis = Mock(set=AsyncMock())
    middleware = UniqueIdMiddleware(rdb=redis)
    message = make_message()
    message.labels['unique_lock_timeout'] = lock_timeout
    with pytest.raises(ValueError):
        await middleware.pre_send(message)
    redis.set.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('execution_timeout', [None, '30'])
async def test_execution_timeout_is_passed_without_resetting_enqueue_timeout(execution_timeout: str | None) -> None:
    redis = Mock(set=AsyncMock(return_value=True), eval=AsyncMock(return_value=1))
    middleware = UniqueIdMiddleware(rdb=redis)
    message = make_message()
    if execution_timeout is not None:
        message.labels['unique_execution_lock_timeout'] = execution_timeout
    await middleware.pre_send(message)
    assert await middleware.acquire_execution(message)
    assert redis.eval.call_args.args[-2:] == (120000, 0 if execution_timeout is None else 30000)
    assert message.labels[middleware.EXECUTION_OWNER_LABEL] != message.labels[middleware.OWNER_LABEL]


@pytest.mark.asyncio
async def test_busy_execution_does_not_claim_ownership_or_release_enqueue() -> None:
    redis = Mock(set=AsyncMock(return_value=True), eval=AsyncMock(return_value=0))
    middleware = UniqueIdMiddleware(rdb=redis)
    message = await middleware.pre_send(make_message())
    enqueue_owner = message.labels[middleware.OWNER_LABEL]
    assert not await middleware.acquire_execution(message)
    assert middleware.EXECUTION_OWNER_LABEL not in message.labels
    assert message.labels[middleware.OWNER_LABEL] == enqueue_owner
    redis.eval.assert_awaited_once()


@pytest.mark.asyncio
async def test_retry_after_enqueue_release_does_not_lose_accepted_work() -> None:
    redis = Mock(set=AsyncMock(return_value=False), eval=AsyncMock(return_value=0))
    middleware = UniqueIdMiddleware(rdb=redis)
    retry = SmartRetryMiddleware(default_retry_label=True)
    broker = InMemoryBroker()
    broker.with_middlewares(middleware, retry)
    message = make_message()
    message.labels[middleware.LOCK_KEY_LABEL] = middleware.get_task_lock_key(
        message.task_name, ['item'], message.kwargs
    )
    message.labels[middleware.OWNER_LABEL] = 'first-enqueue-owner'
    message.labels[middleware.EXECUTION_OWNER_LABEL] = 'first-execution-owner'
    error = RuntimeError('notification failed after successor was queued')
    result: TaskiqResult[None] = TaskiqResult(is_err=True, return_value=None, error=error, execution_time=0)
    with patch.object(broker, 'kick', new_callable=AsyncMock) as kick:
        await retry.on_error(message, result, error)
        kick.assert_awaited_once()
        retried = broker.formatter.loads(kick.call_args.args[0].message)
    assert retried.task_id == message.task_id
    assert middleware.EXECUTION_OWNER_LABEL not in retried.labels
    assert retried.labels[middleware.OWNER_LABEL] != message.labels[middleware.OWNER_LABEL]
