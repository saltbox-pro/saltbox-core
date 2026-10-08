from datetime import datetime
from typing import Any, ClassVar

from pymongo import UpdateOne
from pymongo.errors import DuplicateKeyError

from saltbox_sdk.db.mongo.config import get_mongo_db
from saltbox_sdk.migrations.base_migration import BaseMigration
from saltbox_sdk.migrations.stages.base import BaseMigrationStage, RunPythonMigrationStage

BULK_SIZE = 500
NUMBER_TYPES = ['int', 'float']
PYTHON_TYPES: dict[str, type] = {'bool': bool, 'list': list, 'dict': dict, 'bytes': bytes}

INVENTORY_FIELDS: dict[str, list[dict[str, Any]]] = {
    'batteries': [
        {'name': 'name', 'type': 'str'},
        {'name': 'capacity', 'type': 'str'},
        {'name': 'chemistry', 'type': 'str'},
        {'name': 'manufacturer', 'type': 'str'},
        {'name': 'real_capacity', 'type': 'str'},
        {'name': 'voltage', 'type': 'str'},
        {'name': 'serial', 'type': 'str', 'is_minion_field': True},
    ],
    'bios': [
        {'name': 'bdate', 'type': 'str'},
        {'name': 'bmanufacturer', 'type': 'str'},
        {'name': 'bversion', 'type': 'str'},
        {'name': 'mmanufacturer', 'type': 'str'},
        {'name': 'mmodel', 'type': 'str'},
        {'name': 'smanufacturer', 'type': 'str'},
        {'name': 'smodel', 'type': 'str'},
        {'name': 'assettag', 'type': 'str'},
        {'name': 'msn', 'type': 'str', 'is_minion_field': True},
        {'name': 'ssn', 'type': 'str', 'is_minion_field': True},
    ],
    'controllers': [
        {'name': 'name', 'type': 'str'},
        {'name': 'manufacturer', 'type': 'str'},
        {'name': 'pciid', 'type': 'str', 'is_minion_field': True},
        {'name': 'pcislot', 'type': 'str', 'is_minion_field': True},
    ],
    'cpus': [
        {'name': 'type', 'type': 'str'},
        {'name': 'cores', 'type': 'int'},
        {'name': 'cpuarch', 'type': 'str'},
        {'name': 'manufacturer', 'type': 'str'},
        {'name': 'threads', 'type': 'int'},
    ],
    'drives': [
        {'name': 'volumn', 'type': 'str', 'is_minion_field': True},
        {'name': 'filesystem', 'type': 'str'},
        {'name': 'free', 'type': 'int', 'is_minion_field': True},
        {'name': 'total', 'type': 'int', 'is_minion_field': True},
        {'name': 'type', 'type': 'str'},
    ],
    'hardware': [
        {'name': 'name', 'type': 'str', 'is_minion_field': True},
        {'name': 'osname', 'type': 'str'},
        {'name': 'osversion', 'type': 'str'},
        {'name': 'memory', 'type': 'int', 'is_minion_field': True},
        {'name': 'swap', 'type': 'int', 'is_minion_field': True},
        {'name': 'uuid', 'type': 'str', 'is_minion_field': True},
    ],
    'inputs': [
        {'name': 'caption', 'type': 'str'},
        {'name': 'description', 'type': 'str'},
        {'name': 'type', 'type': 'str'},
    ],
    'softwares': [
        {'name': 'name', 'type': 'str'},
        {'name': 'publisher', 'type': 'str'},
        {'name': 'version', 'type': 'str'},
        {'name': 'arch', 'type': 'str'},
        {'name': 'comments', 'type': 'str'},
        {'name': 'filesize', 'type': 'int', 'is_minion_field': True},
        {'name': 'from_', 'type': 'str', 'is_minion_field': True},
        {'name': 'installdate', 'type': 'str', 'is_minion_field': True},
        {'name': 'system_category', 'type': 'str', 'is_minion_field': True},
    ],
    'local_groups': [
        {'name': 'name', 'type': 'str'},
        {'name': 'gid', 'type': 'str', 'is_minion_field': True},
        {'name': 'members', 'type': 'str', 'is_minion_field': True},
    ],
    'local_users': [
        {'name': 'login', 'type': 'str'},
        {'name': 'name', 'type': 'str'},
        {'name': 'home', 'type': 'str'},
        {'name': 'shell', 'type': 'str'},
        {'name': 'uid', 'type': 'str', 'is_minion_field': True},
    ],
    'memories': [
        {'name': 'caption', 'type': 'str'},
        {'name': 'manufacturer', 'type': 'str'},
        {'name': 'type', 'type': 'str'},
        {'name': 'capacity', 'type': 'int'},
        {'name': 'numslots', 'type': 'int'},
        {'name': 'speed', 'type': 'int'},
    ],
    'monitors': [
        {'name': 'manufacturer', 'type': 'str'},
        {'name': 'model', 'type': 'str'},
        {'name': 'connection_type', 'type': 'str', 'is_minion_field': True},
        {'name': 'diagonal', 'type': 'float'},
        {'name': 'year', 'type': 'int', 'is_minion_field': True},
        {'name': 'serial_number', 'type': 'str', 'is_minion_field': True},
    ],
    'networks': [
        {'name': 'description', 'type': 'str'},
        {'name': 'ipaddress', 'type': 'str', 'is_minion_field': True},
        {'name': 'macaddr', 'type': 'str', 'is_minion_field': True},
        {'name': 'driver', 'type': 'str'},
        {'name': 'speed', 'type': 'str', 'is_minion_field': True},
        {'name': 'status', 'type': 'str', 'is_minion_field': True},
        {'name': 'type', 'type': 'str'},
        {'name': 'ipgateway', 'type': 'str'},
        {'name': 'ipmask', 'type': 'str'},
        {'name': 'ipsubnet', 'type': 'str'},
    ],
    'printers': [
        {'name': 'name', 'type': 'str', 'is_minion_field': True},
        {'name': 'driver', 'type': 'str'},
        {'name': 'port', 'type': 'str', 'is_minion_field': True},
    ],
    'slots': [
        {'name': 'name', 'type': 'str'},
        {'name': 'description', 'type': 'str'},
        {'name': 'status', 'type': 'str', 'is_minion_field': True},
    ],
    'sounds': [
        {'name': 'name', 'type': 'str'},
        {'name': 'description', 'type': 'str'},
        {'name': 'manufacturer', 'type': 'str'},
    ],
    'storages': [
        {'name': 'manufacturer', 'type': 'str'},
        {'name': 'model', 'type': 'str'},
        {'name': 'name', 'type': 'str', 'is_minion_field': True},
        {'name': 'disksize', 'type': 'int'},
        {'name': 'firmware', 'type': 'str'},
        {'name': 'type', 'type': 'str'},
        {'name': 'description', 'type': 'str'},
        {'name': 'serialnumber', 'type': 'str', 'is_minion_field': True},
    ],
    'usbdevices': [
        {'name': 'caption', 'type': 'str'},
        {'name': 'manufacturer', 'type': 'str'},
        {'name': 'class_', 'type': 'str'},
        {'name': 'productid', 'type': 'str'},
        {'name': 'subclass', 'type': 'str'},
        {'name': 'vendorid', 'type': 'str'},
    ],
    'videos': [
        {'name': 'chipset', 'type': 'str'},
        {'name': 'name', 'type': 'str'},
        {'name': 'memory', 'type': 'int'},
        {'name': 'resolution', 'type': 'str', 'is_minion_field': True},
        {'name': 'pciid', 'type': 'str', 'is_minion_field': True},
        {'name': 'psislot', 'type': 'str', 'is_minion_field': True},
    ],
    'virtualmachines': [
        {'name': 'name', 'type': 'str'},
        {'name': 'status', 'type': 'str'},
        {'name': 'subsystem', 'type': 'str'},
        {'name': 'vmtype', 'type': 'str'},
        {'name': 'memory', 'type': 'int'},
        {'name': 'vcpu', 'type': 'int'},
    ],
}


def get_single_type(types: list[str]) -> str:
    types = [field_type for field_type in types if field_type != 'none']

    if not types or 'str' in types:
        return 'str'
    if len(types) == 1:
        return types[0]
    if all(field_type in NUMBER_TYPES for field_type in types):
        return 'float'

    return 'str'


def get_category_fields(category: dict[str, Any]) -> list[dict[str, Any]]:
    if category['source'] == 'inventory' and category['name'] in INVENTORY_FIELDS:
        return [
            {'is_empty_allowed': True, 'is_minion_field': False, **field}
            for field in INVENTORY_FIELDS[category['name']]
        ]

    minion_fields = category.get('minion_fields') or []
    fields = []

    for field in category.get('fields') or []:
        if 'types' not in field:
            fields.append(field)
            continue

        fields.append(
            {
                'name': field['name'],
                'type': get_single_type(field['types']),
                'is_empty_allowed': True,
                'is_minion_field': field['name'] in minion_fields,
            }
        )

    return fields


def cast_to_str(value: Any) -> tuple[bool, Any]:
    if isinstance(value, str):
        return True, value
    if isinstance(value, bool):
        return False, None
    if isinstance(value, int | float):
        return True, str(value)
    if isinstance(value, datetime):
        return True, value.isoformat()

    return False, None


def cast_to_number(value: Any, field_type: str) -> tuple[bool, Any]:
    if isinstance(value, bool):
        return False, None
    if isinstance(value, int):
        return True, value
    if isinstance(value, float):
        if field_type == 'float':
            return True, value
        if value.is_integer():
            return True, int(value)
        return False, None
    if isinstance(value, str):
        try:
            return True, int(value) if field_type == 'int' else float(value)
        except ValueError:
            return False, None

    return False, None


def cast_value(value: Any, field_type: str) -> tuple[bool, Any]:
    if value is None or value == '':
        return True, value
    if field_type == 'str':
        return cast_to_str(value)
    if field_type in NUMBER_TYPES:
        return cast_to_number(value, field_type)
    if field_type == 'datetime':
        if isinstance(value, datetime):
            return True, value
        if isinstance(value, str):
            try:
                return True, datetime.fromisoformat(value)
            except ValueError:
                return False, None
        return False, None

    return isinstance(value, PYTHON_TYPES[field_type]), value


def cast_data(data: dict[str, Any], field_types: dict[str, str], stats: dict[str, int]) -> dict[str, Any]:
    cast: dict[str, Any] = {}

    for key, value in data.items():
        if key not in field_types:
            cast[key] = value
            continue

        is_valid, new_value = cast_value(value, field_types[key])
        if not is_valid:
            stats['dropped_values'] += 1
            continue

        cast[key] = new_value
        if type(new_value) is not type(value) or new_value != value:
            stats['cast_values'] += 1

    return cast


def cast_items(items: list[dict[str, Any]], field_types: dict[str, str], stats: dict[str, int]) -> list[dict[str, Any]]:
    new_items = []

    for item in items:
        data = cast_data(item['data'], field_types, stats)
        if data or not item['data']:
            new_items.append({**item, 'data': data})
        else:
            stats['dropped_items'] += 1

    return new_items


async def cast_static_data(types_by_category: dict[tuple[str, str], dict[str, str]], stats: dict[str, int]) -> None:
    minions = get_mongo_db().get_collection('minions')
    cursor = minions.find({'extra_static': {'$exists': True, '$ne': {}}}, {'extra_static': 1})

    operations: list[UpdateOne] = []

    async for minion in cursor:
        update: dict[str, Any] = {}

        for source, categories in minion['extra_static'].items():
            for name, items in categories.items():
                field_types = types_by_category.get((source, name))
                if field_types is None:
                    continue

                new_items = cast_items(items, field_types, stats)
                if new_items != items:
                    update[f'extra_static.{source}.{name}'] = new_items

        if update:
            operations.append(UpdateOne({'_id': minion['_id']}, {'$set': update}))

        if len(operations) >= BULK_SIZE:
            await minions.bulk_write(operations)
            operations = []

    if operations:
        await minions.bulk_write(operations)


async def cast_aggregated_data(types_by_category: dict[tuple[str, str], dict[str, str]], stats: dict[str, int]) -> None:
    records = get_mongo_db().get_collection('minion_extra_data')

    async for record in records.find({}):
        field_types = types_by_category.get((record['source'], record['name']))
        if field_types is None:
            continue

        data = cast_data(record['data'], field_types, stats)
        entries = []
        for entry in record['minions']:
            entry_data = cast_data(entry['data'], field_types, stats)
            if data or entry_data or not (record['data'] or entry['data']):
                entries.append({**entry, 'data': entry_data})
            else:
                stats['dropped_items'] += 1

        if not data and not entries:
            await records.delete_one({'_id': record['_id']})
            stats['deleted_records'] += 1
            continue

        if data == record['data'] and entries == record['minions']:
            continue

        try:
            await records.update_one({'_id': record['_id']}, {'$set': {'data': data, 'minions': entries}})
        except DuplicateKeyError:
            await records.update_one(
                {'source': record['source'], 'name': record['name'], 'data': data},
                {'$push': {'minions': {'$each': entries}}},
            )
            await records.delete_one({'_id': record['_id']})
            stats['merged_records'] += 1


async def migrate_extra_fields_to_single_type() -> str:
    categories = get_mongo_db().get_collection('minion_extra_data_category')
    types_by_category: dict[tuple[str, str], dict[str, str]] = {}

    async for category in categories.find({}):
        fields = get_category_fields(category)
        await categories.update_one(
            {'_id': category['_id']}, {'$set': {'fields': fields}, '$unset': {'minion_fields': ''}}
        )
        types_by_category[(category['source'], category['name'])] = {field['name']: field['type'] for field in fields}

    stats = {
        'cast_values': 0,
        'dropped_values': 0,
        'dropped_items': 0,
        'merged_records': 0,
        'deleted_records': 0,
    }

    await cast_static_data(types_by_category, stats)
    await cast_aggregated_data(types_by_category, stats)

    return (
        f'Migrated {len(types_by_category)} extra data category(ies) to single field types: '
        f'{stats["cast_values"]} value(s) cast, {stats["dropped_values"]} value(s) and '
        f'{stats["dropped_items"]} item(s) dropped, {stats["merged_records"]} aggregated record(s) merged, '
        f'{stats["deleted_records"]} emptied aggregated record(s) deleted'
    )


class Migration(BaseMigration):
    dependencies: ClassVar[list[str]] = [
        'saltbox_core.minion_collections.migrations.0003_identify_extra_aggregated_entries'
    ]
    stages: ClassVar[list[BaseMigrationStage]] = [
        RunPythonMigrationStage(callback=migrate_extra_fields_to_single_type),
    ]
