from datetime import UTC, datetime

import pytest

from saltbox_core.config import SETTINGS
from saltbox_core.jobs.exceptions import JobCreateException
from saltbox_core.jobs.repositories.job_repository import JobRepository
from saltbox_core.jobs.schemas.job_schemas import AUTO_GRAINS_REQUEST_SOURCE
from saltbox_core.jobs.services.job_services import JobService
from saltbox_core.minion_collections.repositories.collection import CollectionRepository
from saltbox_core.minion_collections.repositories.extra_data import ExtraDataRepository
from saltbox_core.minion_collections.repositories.extra_data_category import ExtraDataCategoryRepository
from saltbox_core.minion_collections.repositories.minion import MinionRepository
from saltbox_core.minion_collections.schemas.minion import GrainsSchema, MinionCreateSchema
from saltbox_core.minion_collections.services.minion import MinionService
from saltbox_core.salt.exceptions import StopProcessing
from saltbox_core.salt.handlers.job_error import JobErrorHandler
from saltbox_core.salt.handlers.job_return_handler import JobReturnMessageHandler
from saltbox_core.salt.handlers.minion_started_handler import MinionStartedMessageHandler
from saltbox_core.salt.handlers.new_job_handler import JobNewMessageHandler
from saltbox_core.salt.handlers.presence_handler import PresenceMessageHandler

pytestmark = pytest.mark.asyncio


@pytest.fixture
def minion_service(mocked_db):
    category_repo = ExtraDataCategoryRepository(mocked_db)
    extra_data_repo = ExtraDataRepository(mocked_db, extra_data_category_repository=category_repo)

    return MinionService(
        MinionRepository(
            mocked_db, extra_data_repository=extra_data_repo, collection_repository=CollectionRepository(mocked_db)
        )
    )


async def _create_minion(minion_service, minion_id, master='salt', last_activity=None, grains_id=None):
    await minion_service.create(
        MinionCreateSchema(
            minion_id=minion_id, master=master, grains=GrainsSchema(id=grains_id), last_activity=last_activity
        )
    )


async def test_create_missing(minion_service):
    last_activity = datetime(2026, 11, 1, tzinfo=UTC)
    await _create_minion(minion_service, 'active', last_activity=last_activity, grains_id='active')
    await _create_minion(minion_service, 'active-without-grains', last_activity=last_activity)
    await _create_minion(minion_service, 'never-active-with-grains', grains_id='never-active-with-grains')
    await _create_minion(minion_service, 'never-active')
    await _create_minion(minion_service, 'new', master='other')

    created_ids, existing_ids_needing_grains = await minion_service.create_missing(
        master_id='salt',
        minion_ids=['active', 'active-without-grains', 'never-active-with-grains', 'never-active', 'new', 'new'],
    )

    assert created_ids == ['new']
    assert sorted(existing_ids_needing_grains) == ['active-without-grains', 'never-active', 'never-active-with-grains']
    created = await minion_service.repo.collection.find_one({'minion_id': 'new', 'master': 'salt'})
    assert created['last_activity'] is None
    assert await minion_service.repo.count({}) == 6


@pytest.fixture
def services(mocker):
    minion_service = mocker.MagicMock()
    minion_service.create_missing = mocker.AsyncMock(return_value=(['new'], ['never-active']))
    job_service = mocker.MagicMock()
    job_service.create = mocker.AsyncMock()
    job_service.get_auto_grains_requested_minion_ids = mocker.AsyncMock(return_value=set())

    return minion_service, job_service


def _match(handler, tag):
    return handler.tag_patterns[0].match(tag)


async def test_presence_creates_minions_and_requests_grains(services):
    minion_service, job_service = services
    handler = PresenceMessageHandler(redis_client=None, minion_service=minion_service, job_service=job_service)

    await handler._create_missing_minions(
        match=_match(handler, 'salt/presence/present'), master_id='salt', data={'present': ['new', 'never-active']}
    )

    minion_service.create_missing.assert_awaited_once_with(master_id='salt', minion_ids=['new', 'never-active'])
    job = job_service.create.await_args.kwargs['data']
    assert (job.tgt, job.tgt_type, job.salt_master, job.fun) == (
        ['new', 'never-active'],
        'list',
        'salt',
        'grains.items',
    )
    assert job.source == AUTO_GRAINS_REQUEST_SOURCE
    assert job.ttl == SETTINGS.auto_grains_request_ttl


async def test_minions_with_active_auto_grains_request_are_skipped(services):
    minion_service, job_service = services
    job_service.get_auto_grains_requested_minion_ids.return_value = {'never-active'}
    handler = PresenceMessageHandler(redis_client=None, minion_service=minion_service, job_service=job_service)
    match = _match(handler, 'salt/presence/present')

    await handler._create_missing_minions(match=match, master_id='salt', data={'present': ['new', 'never-active']})

    job_service.get_auto_grains_requested_minion_ids.assert_awaited_once_with(
        master_id='salt', minion_ids=['new', 'never-active']
    )
    assert job_service.create.await_args.kwargs['data'].tgt == ['new']

    job_service.create.reset_mock()
    job_service.get_auto_grains_requested_minion_ids.return_value = {'new', 'never-active'}

    await handler._create_missing_minions(match=match, master_id='salt', data={'present': ['new', 'never-active']})

    job_service.create.assert_not_awaited()


async def test_minion_start_always_requests_grains(services):
    minion_service, job_service = services
    job_service.get_auto_grains_requested_minion_ids.return_value = {'m1'}
    handler = MinionStartedMessageHandler(redis_client=None, minion_service=minion_service, job_service=job_service)
    match = _match(handler, 'salt/minion/m1/start')

    with pytest.raises(StopProcessing):
        await handler.process(match=match, master_id='salt', data={})

    job = job_service.create.await_args.kwargs['data']
    assert (job.tgt, job.tgt_type, job.fun, job.source, job.ttl) == (
        'm1',
        'glob',
        'grains.items',
        AUTO_GRAINS_REQUEST_SOURCE,
        SETTINGS.auto_grains_request_ttl,
    )
    job_service.get_auto_grains_requested_minion_ids.assert_not_awaited()


async def test_get_auto_grains_requested_minion_ids(mocked_db, mocker):
    job_service = JobService(
        rdb=mocker.MagicMock(),
        job_repository=JobRepository(mocked_db),
        task_template_service=mocker.MagicMock(),
        job_return_service=mocker.MagicMock(),
        master_service=mocker.MagicMock(),
    )
    jobs = mocked_db['jobs'].collection
    auto_source = AUTO_GRAINS_REQUEST_SOURCE.model_dump()
    jobs.insert_many(
        [
            {'salt_master': 'salt', 'source': auto_source, 'status': 'starting', 'tgt': ['m1', 'other']},
            {'salt_master': 'salt', 'source': auto_source, 'status': 'running', 'tgt': 'm2'},
            {'salt_master': 'salt', 'source': auto_source, 'status': 'finished', 'tgt': ['m3']},
            {'salt_master': 'salt', 'source': {'type': 'system', 'id': None}, 'status': 'running', 'tgt': ['m4']},
            {'salt_master': 'other', 'source': auto_source, 'status': 'running', 'tgt': ['m5']},
        ]
    )

    requested_ids = await job_service.get_auto_grains_requested_minion_ids(
        master_id='salt', minion_ids=['m1', 'm2', 'm3', 'm4', 'm5']
    )

    assert requested_ids == {'m1', 'm2'}


async def test_job_return_creates_minion(services):
    minion_service, job_service = services
    handler = JobReturnMessageHandler(
        redis_client=None,
        minion_service=minion_service,
        job_service=job_service,
        job_return_service=None,
        broker=None,
    )
    match = _match(handler, 'salt/job/20261102120000000000/ret/new')

    await handler._create_missing_minions(match=match, master_id='salt', data={'fun': 'test.ping'})

    minion_service.create_missing.assert_awaited_once_with(master_id='salt', minion_ids=['new'])
    job_service.create.assert_awaited_once()


async def test_new_grains_job_does_not_request_grains(services):
    minion_service, job_service = services
    handler = JobNewMessageHandler(
        redis_client=None, minion_service=minion_service, job_service=job_service, job_return_service=None
    )
    match = _match(handler, 'salt/job/20261102120000000000/new')

    await handler._create_missing_minions(
        match=match, master_id='salt', data={'fun': 'grains.items', 'minions': ['new']}
    )

    minion_service.create_missing.assert_awaited_once_with(master_id='salt', minion_ids=['new'])
    job_service.create.assert_not_awaited()


async def test_grains_return_does_not_request_grains(services):
    minion_service, job_service = services
    handler = JobReturnMessageHandler(
        redis_client=None, minion_service=minion_service, job_service=job_service, job_return_service=None, broker=None
    )
    match = _match(handler, 'salt/job/20261102120000000000/ret/new')

    await handler._create_missing_minions(match=match, master_id='salt', data={'fun': 'grains.items'})

    minion_service.create_missing.assert_awaited_once_with(master_id='salt', minion_ids=['new'])
    job_service.create.assert_not_awaited()


async def test_handler_without_minions_does_nothing(services):
    minion_service, job_service = services
    handler = JobErrorHandler(redis_client=None, minion_service=minion_service, job_service=job_service)

    await handler._create_missing_minions(
        match=_match(handler, 'saltbox/job/20261102120000000000/error'), master_id='salt', data={}
    )

    minion_service.create_missing.assert_not_awaited()
    job_service.create.assert_not_awaited()


async def test_grains_request_failure_does_not_break_processing(services):
    minion_service, job_service = services
    job_service.create.side_effect = JobCreateException('Master not found')
    handler = PresenceMessageHandler(redis_client=None, minion_service=minion_service, job_service=job_service)

    await handler._create_missing_minions(
        match=_match(handler, 'salt/presence/present'), master_id='salt', data={'present': ['new']}
    )

    minion_service.create_missing.assert_awaited_once()
