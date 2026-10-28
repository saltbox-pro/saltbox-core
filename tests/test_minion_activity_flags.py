import importlib
from datetime import datetime, timedelta

import pytest

from saltbox_core.config import SETTINGS
from saltbox_core.minion_collections.repositories.collection import CollectionRepository
from saltbox_core.minion_collections.repositories.extra_data import ExtraDataRepository
from saltbox_core.minion_collections.repositories.extra_data_category import ExtraDataCategoryRepository
from saltbox_core.minion_collections.repositories.minion import MinionRepository
from saltbox_core.minion_collections.routers.filters import filter_schema
from saltbox_core.minion_collections.schemas.minion import MinionExportSchema, MinionShortSchema
from saltbox_core.minion_collections.services.minion import MinionService
from saltbox_sdk.exceptions import SaltBoxValidationException
from saltbox_sdk.utilities.helpers import utc_now

pytestmark = pytest.mark.asyncio

migration = importlib.import_module('saltbox_core.minion_collections.migrations.0005_rewrite_legacy_extra_filters')


@pytest.fixture
def minion_repo(mocked_db):
    category_repo = ExtraDataCategoryRepository(mocked_db)
    extra_data_repo = ExtraDataRepository(mocked_db, extra_data_category_repository=category_repo)

    return MinionRepository(
        mocked_db, extra_data_repository=extra_data_repo, collection_repository=CollectionRepository(mocked_db)
    )


@pytest.fixture
def minions(minion_repo):
    now = utc_now()
    minion_repo.collection.collection.insert_many(
        [
            {'minion_id': 'missing'},
            {'minion_id': 'none', 'last_activity': None},
            {'minion_id': 'old', 'last_activity': now - timedelta(seconds=SETTINGS.minion_inactive_period + 60)},
            {'minion_id': 'recent', 'last_activity': now},
        ]
    )


async def find_minion_ids(minion_repo, query):
    prepared_query = await minion_repo.__prepare_query__(query)

    return sorted(doc['minion_id'] for doc in minion_repo.collection.collection.find(prepared_query))


@pytest.mark.parametrize('value', [True, {'$eq': True}, {'$ne': False}])
async def test_is_never_active_true(minion_repo, minions, value):
    assert await find_minion_ids(minion_repo, {'is_never_active': value}) == ['missing', 'none']


@pytest.mark.parametrize('value', [False, {'$eq': False}, {'$ne': True}])
async def test_is_never_active_false(minion_repo, minions, value):
    assert await find_minion_ids(minion_repo, {'is_never_active': value}) == ['old', 'recent']


async def test_is_not_active_true_includes_never_active(minion_repo, minions):
    assert await find_minion_ids(minion_repo, {'is_not_active': True}) == ['missing', 'none', 'old']


async def test_is_not_active_false(minion_repo, minions):
    assert await find_minion_ids(minion_repo, {'is_not_active': {'$ne': True}}) == ['recent']


async def test_is_not_active_uses_inactive_period(minion_repo):
    query = await minion_repo.__prepare_query__({'is_not_active': False})

    active_dt = query['last_activity']['$gte']
    assert isinstance(active_dt, datetime)
    assert utc_now() - active_dt >= timedelta(seconds=SETTINGS.minion_inactive_period)


async def test_flags_inside_and(minion_repo, minions):
    query = {'$and': [{'is_never_active': False}, {'is_not_active': True}]}

    assert await find_minion_ids(minion_repo, query) == ['old']


@pytest.mark.parametrize('value', ['true', 1, None, {'$in': [True]}, {'$eq': 'true'}, {'$eq': True, '$ne': False}])
@pytest.mark.parametrize('field', ['is_never_active', 'is_not_active'])
async def test_invalid_flag_filter(minion_repo, field, value):
    with pytest.raises(SaltBoxValidationException):
        await minion_repo.__prepare_query__({field: value})


async def test_flags_are_projected_through_aggregation(minion_repo):
    projection = minion_repo._get_projection_from_model(MinionShortSchema)

    pipeline = await minion_repo.prepare_pipeline(projection, {})

    added_fields = [field for stage in pipeline if '$addFields' in stage for field in stage['$addFields']]
    assert added_fields == ['is_never_active', 'is_not_active']


async def test_is_not_active_aggregation_uses_backend_time(minion_repo):
    pipeline = await minion_repo.prepare_pipeline({'is_not_active': 1}, {})

    is_not_active = pipeline[0]['$addFields']['is_not_active']
    active_dt = is_not_active['$or'][1]['$lt'][1]
    assert isinstance(active_dt, datetime)
    assert utc_now() - active_dt >= timedelta(seconds=SETTINGS.minion_inactive_period)


async def test_process_presence_uses_backend_time(minion_repo):
    minion_repo.collection.collection.insert_one({'minion_id': 'm1', 'master': 'master1', 'last_activity': None})
    started = utc_now().replace(microsecond=0)

    await MinionService(minion_repo).process_presence(master_id='master1', minions=['m1'])

    minion = minion_repo.collection.collection.find_one({'minion_id': 'm1'})
    assert minion['last_activity'] >= started.replace(tzinfo=None)


async def test_sort_by_flag_computes_it_before_sort(minion_repo):
    projection = minion_repo._get_projection_from_model(MinionShortSchema)

    pipeline = await minion_repo.prepare_pipeline(projection, {}, sort={'is_not_active': 1})

    stages = [next(iter(stage)) for stage in pipeline]
    assert stages.index('$addFields') < stages.index('$sort')
    assert stages.count('$addFields') == 2


def test_export_schema_has_no_flags():
    assert 'is_never_active' not in MinionExportSchema.model_fields
    assert 'is_not_active' not in MinionExportSchema.model_fields


async def test_filter_schema(mocker):
    extra_data_category_service = mocker.Mock(get_minion_filter_schema=mocker.AsyncMock(return_value=[]))

    schema = {field.name: field for field in await filter_schema(extra_data_category_service)}

    assert 'extra' not in schema
    for name in ('is_never_active', 'is_not_active'):
        assert [operator.name for operator in schema[name].operators] == ['=']
        assert schema[name].value_editor_type == 'checkbox'
    assert schema['collection'].group == 'collection'
    assert schema['last_activity'].group == 'general'
    assert schema['grains.os'].group == 'grains'
    for field in schema.values():
        assert field.extra_category is None


@pytest.mark.parametrize(
    ('query', 'expected'),
    [
        ({'extra.static.src.name.field': 1}, {'extra.src.name.field': 1}),
        ({'extra.aggregated.src.name.field': 1}, {'extra.src.name.field': 1}),
        (
            {'$and': [{'extra.static.src.name.a.b': {'$in': [1]}}, {'$or': [{'extra.aggregated.s.n.f': 2}]}]},
            {'$and': [{'extra.src.name.a.b': {'$in': [1]}}, {'$or': [{'extra.s.n.f': 2}]}]},
        ),
        ({'extra.src.name.field': 1, 'grains.os': 'ALT'}, {'extra.src.name.field': 1, 'grains.os': 'ALT'}),
        ({'extra.static.cat.field': 1}, {'extra.static.cat.field': 1}),
        ({'extra.static.other.field.sub': 1}, {'extra.other.field.sub': 1}),
    ],
)
def test_migration_rewrites_legacy_extra_keys(query, expected):
    assert migration.rewrite_query(query, {('static', 'cat')}) == expected
