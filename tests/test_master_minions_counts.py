from datetime import datetime, timedelta

import pytest

from saltbox_core.masters.repositories.master_repository import MasterRepository, MinionsActivityGroupStage
from saltbox_core.masters.schemas.master_schemas import MasterViewSchema

pytestmark = pytest.mark.asyncio

ACTIVE_DT = datetime(2026, 1, 1)


@pytest.fixture
def master_repo(mocked_db, mocker):
    mocker.patch('saltbox_core.minion_collections.utils.activity_filter.get_minion_active_dt', return_value=ACTIVE_DT)

    return MasterRepository(mocked_db)


async def test_counts_share_one_minions_lookup(master_repo):
    projection = master_repo._get_projection_from_model(MasterViewSchema)

    pipeline = await master_repo.prepare_pipeline(projection, {})

    stages = [next(iter(stage)) for stage in pipeline]
    assert stages.count('$lookup') == 1
    assert stages.count('$unwind') == 1


async def test_only_minions_count_skips_activity_fields(master_repo):
    pipeline = await master_repo.prepare_pipeline({'minions_count': 1}, {})

    added_fields = [field for stage in pipeline if '$addFields' in stage for field in stage['$addFields']]
    assert added_fields == ['minions_count']


async def test_minions_activity_group_counts(master_repo, mocked_db):
    collection = mocked_db['minions'].collection
    collection.insert_many(
        [
            {'minion_id': 'missing'},
            {'minion_id': 'none', 'last_activity': None},
            {'minion_id': 'old', 'last_activity': ACTIVE_DT - timedelta(minutes=1)},
            {'minion_id': 'recent', 'last_activity': ACTIVE_DT},
        ]
    )

    rows = list(collection.aggregate([MinionsActivityGroupStage().render_stage()]))

    assert rows == [{'_id': None, 'total': 4, 'never_active': 2, 'not_active': 3}]
