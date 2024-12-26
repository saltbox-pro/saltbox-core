import logging.config
from collections.abc import Callable
from types import UnionType
from typing import Any, Union, get_args, get_origin

from fastapi import HTTPException, status

from fastms_core.config import LOG_CONFIG
from fastms_core.minions.schemas import GrainsSchema, MinionSchema

logging.config.dictConfig(LOG_CONFIG.model_dump())

logger = logging.getLogger(__name__)


class MongoPiplineBuilder:
    """MongoDB aggregation pipeline builder"""

    def __init__(self, field_name: str):
        self.field_name = field_name
        self.field_type = self._detect_field_type()

    @property
    def _field_handler_map(self) -> dict[str, Callable[..., list]]:
        return {
            'grains.pythonversion': self._list_to_str_handler,
            'grains.hwaddr_interfaces': self._unique_keys_handler,
        }

    def _detect_field_type(self) -> type[Any] | None:
        """Detect field type by field name"""

        if self.field_name.startswith('grains.'):
            field_type = GrainsSchema.model_fields[self.field_name.split('.')[1]].annotation
        else:
            field_type = MinionSchema.model_fields[self.field_name].annotation

        return field_type

    def _is_allowed_field_types(self) -> bool:
        if self.field_type is str:
            return True
        if self._is_union():
            types = get_args(self.field_type)
            if types == (str, type(None)):
                return True
        return False

    def _is_union(self) -> bool:
        origin = get_origin(self.field_type)
        return origin is Union or origin is UnionType

    def _list_to_str_handler(self) -> list:
        pipeline = [
            {
                '$project': {
                    'field_str': {
                        '$reduce': {
                            'input': f'${self.field_name}',
                            'initialValue': '',
                            'in': {
                                '$concat': [
                                    {'$cond': [{'$eq': ['$$value', '']}, '', {'$concat': ['$$value', '.']}]},
                                    {'$toString': '$$this'},
                                ]
                            },
                        }
                    }
                }
            },
            {'$group': {'_id': '$field_str', 'count': {'$sum': 1}}},
            {'$project': {'_id': 0, 'value': '$_id', 'count': 1}},
            {'$sort': {'count': -1}},
        ]
        return pipeline

    def _separate_list_items_handler(self) -> list:
        pipline = [
            {'$unwind': f'${self.field_name}'},
            {'$group': {'_id': f'${self.field_name}', 'count': {'$sum': 1}}},
            {'$project': {'value': '$_id', 'count': 1, '_id': 0}},
            {'$sort': {'count': -1}},
        ]

        return pipline

    def _str_handler(self) -> list:
        pipeline = [
            {'$group': {'_id': f'${self.field_name}', 'count': {'$sum': 1}}},
            {'$project': {'value': '$_id', 'count': 1, '_id': 0}},
            {'$sort': {'count': -1}},
        ]

        return pipeline

    def _dict_handler(self) -> list:
        pipeline = [
            {'$project': {f'{self.field_name}': 1}},
            {'$unwind': f'${self.field_name}'},
            {'$group': {'_id': {'k': f'${self.field_name}', 'v': f'${self.field_name}'}, 'count': {'$sum': 1}}},
            {'$project': {'value': '$_id.v', 'count': 1, '_id': 0}},
            {'$sort': {'count': -1}},
        ]

        return pipeline

    def _unique_keys_handler(self) -> list:
        pipeline = [
            {'$project': {f'{self.field_name}': {'$objectToArray': f'${self.field_name}'}}},
            {'$unwind': f'${self.field_name}'},
            {'$group': {'_id': f'${self.field_name}.k', 'count': {'$sum': 1}}},
            {'$project': {'value': '$_id', 'count': 1, '_id': 0}},
            {'$sort': {'count': -1}},
        ]
        return pipeline

    def _get_handler(self) -> Callable[..., list]:
        if self.field_name in self._field_handler_map:
            return self._field_handler_map[self.field_name]
        if self._is_allowed_field_types():
            return self._str_handler
        msg = f'Unsupported field: {self.field_name}'
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    def build(self) -> list:
        return self._get_handler()()
