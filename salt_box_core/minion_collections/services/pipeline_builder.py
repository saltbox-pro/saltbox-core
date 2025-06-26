from collections.abc import Callable
from types import UnionType
from typing import Any, Union, get_args, get_origin

from salt_box_core.config import logger
from salt_box_core.http_errors import BadRequest
from salt_box_core.minion_collections.schemas.minion_schemas import GrainsSchema, MinionModel

LIST_HANDLER_FIELDS = [
    'grains.fqdns',
    'grains.cpu_flags',
    'grains.osrelease_info',
    'grains.ipv4',
    'grains.ipv6',
    'grains.fqdn_ip4',
    'grains.fqdn_ip6',
    'grains.disks',
    'grains.systempath',
    'grains.pythonpath',
    'grains.ssds',
]
LIST_TO_STR_FIELDS = ['grains.pythonversion', 'grains.saltversioninfo']


class MongoPipelineBuilder:
    """MongoDB aggregation pipeline builder"""

    def __init__(self, field_name: str, query: dict | None = None, skip: int = 0, limit: int | None = 100) -> None:
        self.field_name = field_name
        self.limit = limit
        self.skip = skip
        self.field_type = self._detect_field_type()
        self.query = query
        self.pipeline: list[dict[str, Any]] = (
            [
                {'$match': self.query},
            ]
            if self.query
            else []
        )

    @property
    def _field_handler_map(self) -> dict[str, Callable[..., None]]:
        handler_mapping = {
            'grains.hwaddr_interfaces': self._unique_keys_handler,
            'created': self._datetime_handler,
            'modified': self._datetime_handler,
        }
        for field in LIST_HANDLER_FIELDS:
            handler_mapping[field] = self._separate_list_items_handler
        for field in LIST_TO_STR_FIELDS:
            handler_mapping[field] = self._list_to_str_handler
        return handler_mapping

    def _detect_field_type(self) -> type[Any] | None:
        """Detect field type by field name"""

        if self.field_name.startswith('grains.'):
            field_type = GrainsSchema.model_fields[self.field_name.split('.')[1]].annotation
        else:
            field_type = MinionModel.model_fields[self.field_name].annotation

        return field_type

    def _is_allowed_field_types(self) -> bool:
        if self.field_type in [str, int]:
            return True
        if self._is_union():
            types = get_args(self.field_type)
            if types == (str, type(None)) or types == (int, type(None)):
                return True
        return False

    def _is_union(self) -> bool:
        origin = get_origin(self.field_type)
        return origin is Union or origin is UnionType

    def _datetime_handler(self) -> None:
        self.pipeline.extend(
            [
                {
                    '$group': {
                        '_id': {'$dateToString': {'format': '%Y-%m-%d', 'date': f'${self.field_name}'}},
                        'count': {'$sum': 1},
                    }
                },
                {'$project': {'value': '$_id', 'count': 1, '_id': 0}},
                {'$sort': {'value': 1}},
            ]
        )

    def _list_to_str_handler(self) -> None:
        self.pipeline.extend(
            [
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
        )

    def _separate_list_items_handler(self) -> None:
        self.pipeline.extend(
            [
                {'$unwind': f'${self.field_name}'},
                {'$group': {'_id': f'${self.field_name}', 'count': {'$sum': 1}}},
                {'$project': {'value': '$_id', 'count': 1, '_id': 0}},
                {'$sort': {'count': -1}},
            ]
        )

    def _str_int_handler(self) -> None:
        self.pipeline.extend(
            [
                {'$group': {'_id': f'${self.field_name}', 'count': {'$sum': 1}}},
                {'$project': {'value': '$_id', 'count': 1, '_id': 0}},
                {'$sort': {'count': -1}},
            ]
        )

    def _dict_handler(self) -> None:
        self.pipeline.extend(
            [
                {'$project': {f'{self.field_name}': 1}},
                {'$unwind': f'${self.field_name}'},
                {'$group': {'_id': {'k': f'${self.field_name}', 'v': f'${self.field_name}'}, 'count': {'$sum': 1}}},
                {'$project': {'value': '$_id.v', 'count': 1, '_id': 0}},
                {'$sort': {'count': -1}},
            ]
        )

    def _unique_keys_handler(self) -> None:
        self.pipeline.extend(
            [
                {'$project': {f'{self.field_name}': {'$objectToArray': f'${self.field_name}'}}},
                {'$unwind': f'${self.field_name}'},
                {'$group': {'_id': f'${self.field_name}.k', 'count': {'$sum': 1}}},
                {'$project': {'value': '$_id', 'count': 1, '_id': 0}},
                {'$sort': {'count': -1}},
            ]
        )

    def _build_pipeline(self) -> None:
        if self.field_name in self._field_handler_map:
            logger.debug('Apply custom handler %s', self._field_handler_map[self.field_name].__name__)
            self._field_handler_map[self.field_name]()
            return
        if self._is_allowed_field_types():
            logger.debug('Apply str handler')
            self._str_int_handler()
            return
        raise BadRequest(detail=f'Unsupported field: {self.field_name}') from None

    def build(self) -> list:
        self._build_pipeline()
        if self.skip:
            self.pipeline.extend([{'$skip': self.skip}])
        if self.limit:
            self.pipeline.extend([{'$limit': self.limit}])
        return self.pipeline
