from enum import StrEnum
from typing import Any


class UniqueValueKind(StrEnum):
    VALUE = 'value'
    LIST_ITEMS = 'list_items'
    DICT_KEYS = 'dict_keys'
    JOINED_LIST = 'joined_list'
    DATE = 'date'


def build_unique_values_stages(value_path: str, minion_path: str, kind: UniqueValueKind) -> list[dict[str, Any]]:
    value: Any = f'${value_path}'

    if kind == UniqueValueKind.DICT_KEYS:
        value = {'$map': {'input': {'$objectToArray': value}, 'in': '$$this.k'}}
    elif kind == UniqueValueKind.JOINED_LIST:
        value = {
            '$reduce': {
                'input': value,
                'initialValue': '',
                'in': {
                    '$concat': [
                        {'$cond': [{'$eq': ['$$value', '']}, '', {'$concat': ['$$value', '.']}]},
                        {'$toString': '$$this'},
                    ]
                },
            }
        }
    elif kind == UniqueValueKind.DATE:
        value = {'$dateToString': {'format': '%Y-%m-%d', 'date': value}}

    stages: list[dict[str, Any]] = [{'$project': {'_id': 0, 'value': value, 'minion': f'${minion_path}'}}]

    if kind in (UniqueValueKind.LIST_ITEMS, UniqueValueKind.DICT_KEYS):
        stages.append({'$unwind': '$value'})

    stages.extend(
        [
            {'$group': {'_id': {'value': '$value', 'minion': '$minion'}}},
            {'$group': {'_id': '$_id.value', 'count': {'$sum': 1}}},
            {'$project': {'_id': 0, 'value': '$_id', 'count': 1}},
            {'$sort': {'count': -1, 'value': 1}},
        ]
    )

    return stages
