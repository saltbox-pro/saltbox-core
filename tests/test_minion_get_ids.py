from datetime import UTC, datetime
from typing import Any

import pytest
from pytest_mock import MockerFixture

from saltbox_core.minion_collections.repositories.collection import CollectionRepository
from saltbox_core.minion_collections.repositories.extra_data import ExtraDataRepository
from saltbox_core.minion_collections.repositories.extra_data_category import ExtraDataCategoryRepository
from saltbox_core.minion_collections.repositories.minion import MinionRepository
from saltbox_core.minion_collections.schemas.extra_data_category import ExtraDataCategoryModel
from saltbox_sdk.db.mongo.schemas_base import EmptyModel, PyObjectId

pytestmark = pytest.mark.asyncio


@pytest.fixture
def repo(mocked_db: Any) -> MinionRepository:
    categories = ExtraDataCategoryRepository(mocked_db)
    return MinionRepository(mocked_db, ExtraDataRepository(mocked_db, categories), CollectionRepository(mocked_db))


@pytest.mark.parametrize('query', [{}, {'master': 'm1'}, {'master': 'missing'}, {'is_never_active': True}])
async def test_simple_filters_match_list_without_aggregation(
    repo: MinionRepository, mocked_db: Any, mocker: MockerFixture, query: dict[str, Any]
) -> None:
    mocked_db.db['minions'].insert_many(
        [
            {'master': 'm1', 'last_activity': None},
            {'master': 'm2', 'last_activity': datetime.now(UTC)},
        ]
    )
    session = mocker.MagicMock()
    find = mocker.spy(repo.collection, 'find')
    actual = await repo.get_ids(query, session=session)
    assert find.call_count == 1
    assert find.call_args.kwargs['projection'] == {'_id': 1}
    assert find.call_args.kwargs['session'] is session
    expected = await repo.get_list(query, projection_model=EmptyModel)
    assert actual == [item.id for item in expected]


async def test_collection_reference(repo: MinionRepository, mocked_db: Any) -> None:
    result = mocked_db.db['minions'].insert_many(
        [
            {'grains': {'os': 'ALT'}},
            {'grains': {'os': 'other'}},
        ]
    )
    await repo.collection_repository.collection.insert_one(
        {
            'slug': 'alt',
            'title': 'ALT',
            'parent_id': None,
            'query': {'grains.os': 'ALT'},
        }
    )
    assert await repo.get_ids({'collection': {'$in': ['alt']}}) == [result.inserted_ids[0]]
    assert await repo.get_ids({'collection': {'$nin': ['alt']}}) == [result.inserted_ids[1]]


@pytest.mark.parametrize('category_type', ['static', 'aggregated'])
async def test_extra_filter_cast_and_single_preparation(
    repo: MinionRepository, mocked_db: Any, mocker: MockerFixture, category_type: str
) -> None:
    result = mocked_db.db['minions'].insert_many(
        [
            {'extra_static': {'manual': {'assets': [{'data': {'number': 42}}]}}},
            {'extra_static': {'manual': {'assets': [{'data': {'number': 7}}]}}},
        ]
    )
    category = ExtraDataCategoryModel.model_validate(
        {
            '_id': PyObjectId(),
            'created': datetime.now(UTC),
            'modified': datetime.now(UTC),
            'source': 'manual',
            'name': 'assets',
            'type': category_type,
            'fields': [{'name': 'number', 'type': 'int'}],
        }
    )
    await repo.extra_data_repository.extra_data_category_repository.collection.insert_one(
        category.model_dump(by_alias=True)
    )
    lookup = mocker.patch.object(
        repo.extra_data_repository,
        'get_minion_ids_by_filter',
        return_value=[result.inserted_ids[0]],
    )
    assert await repo.get_ids({'extra.manual.assets.number': '42'}) == [result.inserted_ids[0]]
    if category_type == 'aggregated':
        lookup.assert_awaited_once_with(source='manual', name='assets', query={'number': 42})
    else:
        lookup.assert_not_awaited()


async def test_pipeline_keeps_id_projection_and_session(repo: MinionRepository, mocker: MockerFixture) -> None:
    expected = PyObjectId()
    cursor = mocker.Mock()
    cursor.to_list = mocker.AsyncMock(return_value=[{'_id': expected}])
    aggregate = mocker.AsyncMock(return_value=cursor)
    mocker.patch.object(repo.collection, 'aggregate', aggregate, create=True)
    find = mocker.spy(repo.collection, 'find')
    query = {'extra_aggregated.manual.assets.number': 42}
    session = mocker.MagicMock()
    assert await repo.get_ids(query, session=session) == [expected]
    aggregate.assert_awaited_once()
    assert aggregate.call_args.kwargs['session'] is session
    pipeline = aggregate.call_args.kwargs['pipeline']
    assert any('$lookup' in stage for stage in pipeline)
    assert {'$match': query} in pipeline
    assert pipeline[-1] == {'$project': {'_id': 1}}
    find.assert_not_called()
