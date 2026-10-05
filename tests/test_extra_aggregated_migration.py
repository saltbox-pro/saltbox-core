import importlib
from datetime import UTC, datetime

from bson import ObjectId

migration = importlib.import_module('saltbox_core.minion_collections.migrations.0003_identify_extra_aggregated_entries')

UPDATED_AT = datetime(2026, 9, 1, tzinfo=UTC)


def test_identifies_legacy_entry():
    minion_id = ObjectId()

    entry = migration.identify_entry({'minion_id': minion_id, 'data': {'serial': 'S-1', 'updated_at': UPDATED_AT}})

    assert isinstance(entry['_id'], ObjectId)
    assert entry == {
        '_id': entry['_id'],
        'minion_id': minion_id,
        'is_system': True,
        'updated_at': UPDATED_AT,
        'data': {'serial': 'S-1'},
    }


def test_legacy_entry_without_updated_at_gets_current_time():
    entry = migration.identify_entry({'minion_id': ObjectId(), 'data': {}})

    assert entry['updated_at'] is not None
    assert entry['data'] == {}


def test_identified_entry_is_left_alone():
    entry = {'_id': ObjectId(), 'minion_id': ObjectId(), 'is_system': False, 'updated_at': UPDATED_AT, 'data': {}}

    assert migration.identify_entry(entry) is None
