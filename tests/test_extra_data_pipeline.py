from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from saltbox_core.minion_collections.repositories.extra_data import ExtraDataRepository
from saltbox_core.minion_collections.repositories.minion import MinionRepository
from saltbox_core.minion_collections.schemas.extra_data_category import ExtraDataCategoryModel
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.event_bus.schemas import ExtraDataCategoryType


def _build(group_by_fields):
    return MinionRepository.build_extra_data_pipeline(
        category_source='manual',
        category_name='notes',
        category_type=ExtraDataCategoryType.STATIC,
        group_by_fields=group_by_fields,
    )


@pytest.mark.parametrize('group_by_fields', [[], ['text']])
def test_grouped_pipeline_counts_minions_even_without_category_fields(group_by_fields):
    group_stages = [stage['$group'] for stage in _build(group_by_fields) if '$group' in stage]

    assert len(group_stages) == 1
    assert '_minions' in group_stages[0]


def test_ungrouped_pipeline_does_not_count_minions():
    group_stages = [stage['$group'] for stage in _build(None) if '$group' in stage]

    assert group_stages == [{'_id': '$$ROOT'}]


@pytest.mark.parametrize('group_by_fields', [None, [], ['text']])
def test_pipeline_ends_with_sort_and_has_no_facet(group_by_fields):
    pipeline = _build(group_by_fields)

    assert '$sort' in pipeline[-1]
    assert not any('$facet' in stage for stage in pipeline)


class _Cursor:
    async def to_list(self):
        return []


class _Collection:
    def __init__(self):
        self.pipeline = None

    async def aggregate(self, pipeline, session=None):
        self.pipeline = pipeline
        return _Cursor()


class _CategoryRepository:
    def __init__(self, category):
        self.category = category

    async def get(self, query):
        return self.category


async def _prefilters(query):
    category = ExtraDataCategoryModel(
        _id=PyObjectId(),
        created=datetime(2026, 9, 1, tzinfo=UTC),
        modified=datetime(2026, 9, 1, tzinfo=UTC),
        source='manual',
        name='monitors',
        type='aggregated',
        fields=[
            {'name': 'serial', 'type': 'str'},
            {'name': 'serial_number', 'type': 'str', 'is_minion_field': True},
            {'name': 'specs', 'type': 'dict'},
        ],
    )
    repository = ExtraDataRepository.__new__(ExtraDataRepository)
    repository.extra_data_category_repository = _CategoryRepository(category)
    collection = _Collection()

    with patch.object(ExtraDataRepository, 'collection', collection):
        await repository.get_minion_ids_by_filter('manual', 'monitors', query)

    return [stage['$match'] for stage in collection.pipeline[1:] if '$match' in stage][:-1]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('query', 'expected'),
    [
        ({'serial_number': 'SN1'}, [{'minions.data.serial_number': 'SN1'}]),
        ({'serial': 'SN1'}, [{'data.serial': 'SN1'}]),
        ({'specs.size': 24}, [{'data.specs.size': 24}]),
        ({'serialx': 'SN1'}, []),
    ],
)
async def test_minion_ids_filter_prefilters_match_exact_field_names(query, expected):
    assert await _prefilters(query) == expected
