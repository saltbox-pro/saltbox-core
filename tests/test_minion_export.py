import pytest

from saltbox_core.minion_collections.repositories.extra_data import ExtraDataRepository
from saltbox_core.minion_collections.repositories.extra_data_category import ExtraDataCategoryRepository
from saltbox_core.minion_collections.repositories.minion import MinionRepository
from saltbox_core.minion_collections.services.minion import MinionService
from saltbox_sdk.db.mongo.schemas_base import SortOrder


def _build_service(mocked_db):
    category_repo = ExtraDataCategoryRepository(mocked_db)
    extra_data_repo = ExtraDataRepository(mocked_db, extra_data_category_repository=category_repo)

    return MinionService(MinionRepository(mocked_db, extra_data_repository=extra_data_repo))


@pytest.mark.asyncio
async def test_iter_export_rows(mocked_db):
    minion_service = _build_service(mocked_db)
    await minion_service.process_grains(
        'master1', 'm2', {'os': 'ALT', 'efi-secure-boot': True, 'custom_grain': ['a', 'b']}
    )
    await minion_service.process_grains('master1', 'm1', {'os': 'Astra'})
    await minion_service.process_grains('master2', 'm3', {'os': 'ALT'})

    rows = [
        row async for row in minion_service.iter_export_rows({'master': 'master1'}, sort={'minion_id': SortOrder.ASC})
    ]

    assert [row['minion_id'] for row in rows] == ['m1', 'm2']
    assert rows[1]['grains.os'] == 'ALT'
    assert rows[1]['grains.efi-secure-boot'] is True
    assert rows[1]['grains.custom_grain'] == ['a', 'b']
    assert {'id', 'master', 'last_activity', 'created', 'modified'} <= rows[0].keys()
    assert 'grains' not in rows[0]
    assert 'extra' not in rows[0]
