import pytest

from saltbox_sdk.db.mongo.aggregations import AddFieldsAggregationStage, AggregatedField, AggregationsStore


@pytest.mark.parametrize(
    ('field_name', 'matches'),
    [
        ('extra', True),
        ('extra.source.category', True),
        ('extra_static.sbx_bench_extra.profile.data.managed', False),
        ('nested.extra.source', False),
        ('extra_aggregated.source', False),
        ('some_extra.source', False),
    ],
)
def test_aggregation_selection_requires_field_path_prefix(field_name: str, matches: bool) -> None:
    store = AggregationsStore([
        AggregatedField(field_name='extra', stages=[AddFieldsAggregationStage(fields={'extra': {}})]),
    ])
    expected = [{'$addFields': {'extra': {}}}] if matches else []
    assert store.build_pipeline([field_name]) == expected
