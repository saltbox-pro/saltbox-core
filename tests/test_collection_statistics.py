from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from saltbox_core.minion_collections.repositories.collection_membership import get_collection_membership_repository
from saltbox_core.minion_collections.routers.collections import router
from saltbox_core.minion_collections.services.collection import get_collection_service
from saltbox_sdk.db.mongo.schemas_base import PyObjectId


@pytest.fixture
def statistics_client():
    collection_id = PyObjectId()
    service = SimpleNamespace(get_by_slug=AsyncMock(return_value=SimpleNamespace(id=collection_id)))
    repo = SimpleNamespace(
        get_count_events=AsyncMock(
            return_value=[
                (datetime(2026, 1, 2, tzinfo=UTC), 2),
                (datetime(2026, 1, 3, tzinfo=UTC), -2),
            ]
        )
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_collection_service] = lambda: service
    app.dependency_overrides[get_collection_membership_repository] = lambda: repo
    with TestClient(app) as client:
        yield client, repo, service, collection_id


def test_statistics_http(statistics_client):
    client, repo, service, collection_id = statistics_client
    response = client.get(
        '/collections/demo/statistics/minions-count',
        params={
            'from': '2026-01-01T00:00:00Z',
            'to': '2026-01-04T00:00:00Z',
            'interval': 'day',
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body['history_from'] == '2026-01-02T00:00:00Z'
    assert [point['count'] for point in body['points']] == [None, 2, 0, 0]
    service.get_by_slug.assert_awaited_once_with('demo')
    repo.get_count_events.assert_awaited_once_with(collection_id)


@pytest.mark.parametrize(
    'override',
    [
        {'from': '2026-01-05T00:00:00Z'},
        {'from': '2026-01-01T00:00:00'},
        {'interval': 'year'},
        {'timezone': 'Invalid/Zone'},
    ],
)
def test_statistics_validation(statistics_client, override):
    client, repo, _, _ = statistics_client
    params = {'from': '2026-01-01T00:00:00Z', 'to': '2026-01-04T00:00:00Z', 'interval': 'day'}
    response = client.get('/collections/demo/statistics/minions-count', params=params | override)
    assert response.status_code == 422
    repo.get_count_events.assert_not_awaited()


def test_statistics_empty_history(statistics_client):
    client, repo, _, _ = statistics_client
    repo.get_count_events.return_value = []
    response = client.get(
        '/collections/demo/statistics/minions-count',
        params={
            'from': '2026-01-01T00:00:00Z',
            'to': '2026-01-01T00:00:00Z',
            'interval': 'day',
        },
    )
    assert response.status_code == 200
    assert response.json()['history_from'] is None
    assert response.json()['points'] == [{'timestamp': '2026-01-01T00:00:00Z', 'count': None}]


def test_statistics_openapi(statistics_client):
    client, _, _, _ = statistics_client
    schema = client.get('/openapi.json').json()
    operation = schema['paths']['/collections/{slug}/statistics/minions-count']['get']
    assert all(parameter.get('description') for parameter in operation['parameters'])
    for name in ('CollectionCountPoint', 'CollectionCountStatistics'):
        assert all(field.get('description') for field in schema['components']['schemas'][name]['properties'].values())
