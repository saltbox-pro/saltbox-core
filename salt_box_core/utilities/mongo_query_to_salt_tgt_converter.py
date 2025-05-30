import json
from typing import Any, ClassVar

from salt_box_core.minion_collections.schemas.collection_schemas import CollectionModel


class MongoQueryToSaltTgtConverterUnknownKey(Exception):
    pass


class MongoQueryToSaltTgtConverterUnsupportedOperator(Exception):
    pass


class MongoQueryToSaltTgtConverterInvalidValue(Exception):
    pass


class MongoQueryToSaltTgtConverter:
    """
    Mongo-query to salt tgt converter
    """

    QUERY_AND_OPERATOR = '$and'
    QUERY_OR_OPERATOR = '$or'
    QUERY_NOT_EQUAL_OPERATOR = '$ne'
    QUERY_REGEX_OPERATOR = '$regex'
    QUERY_NOT_OPERATOR = '$not'
    QUERY_IN_OPERATOR = '$in'
    QUERY_NOT_IN_OPERATOR = '$nin'
    QUERY_GT_OPERATOR = '$gt'
    QUERY_GTE_OPERATOR = '$gte'
    QUERY_LT_OPERATOR = '$lt'
    QUERY_LTE_OPERATOR = '$lte'

    TGT_AND_OPERATOR = 'and'
    TGT_OR_OPERATOR = 'or'

    QUERY_COMPARISONS_OPERATORS: ClassVar[list[str]] = [
        QUERY_AND_OPERATOR,
        QUERY_OR_OPERATOR,
    ]

    QUERY_UNSUPPORTED_LOOKUPS_OPERATORS: ClassVar[list[str]] = [
        QUERY_GT_OPERATOR,
        QUERY_GTE_OPERATOR,
        QUERY_LT_OPERATOR,
        QUERY_LTE_OPERATOR,
    ]

    QUERY_TO_TGT_CONTAINS_OPERATORS_MAP: ClassVar[dict[str, str]] = {
        QUERY_AND_OPERATOR: TGT_AND_OPERATOR,
        QUERY_OR_OPERATOR: TGT_OR_OPERATOR,
    }

    @classmethod
    def convert_from_minions_collection_obj(cls, minions_collection_obj: CollectionModel) -> str:
        return cls.__convert_to_tgt(query_dict=minions_collection_obj.full_query)

    @classmethod
    def convert_from_dict(cls, query_dict: dict) -> str:
        return cls.__convert_to_tgt(query_dict=query_dict)

    @classmethod
    def convert_from_str(cls, query_str: str) -> str:
        return cls.__convert_to_tgt(query_dict=json.loads(query_str))

    @classmethod
    def __convert_to_tgt(cls, query_dict: dict) -> str:  # noqa: C901
        def process(data: dict, comparison_op: str = cls.QUERY_AND_OPERATOR) -> str:  # noqa: C901
            result_list: list = []

            def process_group(group_items: list, group_op: str) -> str:
                group_result_list: list[str] = []

                for item in group_items:
                    group_result_list.append(process(data=item, comparison_op=group_op))

                if len(group_result_list) > 1:
                    return f'( {f" {cls.QUERY_TO_TGT_CONTAINS_OPERATORS_MAP[group_op]} ".join(group_result_list)} )'

                return group_result_list[0]

            def process_key(query_key: str, tgt_type_letter: str = 'G') -> str:
                if query_key == 'minion_id':
                    return f'{tgt_type_letter}@id'
                if query_key.startswith('grains.'):
                    return f'{tgt_type_letter}@{key[7:]}'

                raise MongoQueryToSaltTgtConverterUnknownKey()

            def process_value(p_value: Any) -> Any:
                if isinstance(p_value, str) and p_value == 'null':
                    return None

                return p_value

            def process_item(item_key: str, item_value: dict | str) -> str:
                if isinstance(item_value, dict):
                    query_op, query_item_value = next(iter(item_value.items()))

                    if query_op in cls.QUERY_UNSUPPORTED_LOOKUPS_OPERATORS:
                        _msg = f'Operator "{query_op}" is not supported'
                        raise MongoQueryToSaltTgtConverterUnsupportedOperator(_msg)

                    if query_op == cls.QUERY_NOT_EQUAL_OPERATOR:
                        return f'not {process_key(query_key=item_key)}:{process_value(query_item_value)}'
                    if query_op == cls.QUERY_REGEX_OPERATOR:
                        return (
                            f'{process_key(query_key=item_key, tgt_type_letter="P")}:{process_value(query_item_value)}'
                        )
                    if query_op in [cls.QUERY_IN_OPERATOR, cls.QUERY_NOT_IN_OPERATOR]:
                        if not isinstance(query_item_value, list):
                            raise MongoQueryToSaltTgtConverterInvalidValue()

                        query_item_value = '|'.join(map(str, query_item_value))
                        tgt_str = f'{process_key(query_key=item_key, tgt_type_letter="P")}:({query_item_value})'

                        if query_op == cls.QUERY_NOT_IN_OPERATOR:
                            tgt_str = f'not {tgt_str}'

                        return tgt_str
                    if query_op == cls.QUERY_NOT_OPERATOR:
                        if (
                            not isinstance(query_item_value, dict)
                            and cls.QUERY_REGEX_OPERATOR not in query_item_value.keys()
                        ):
                            raise MongoQueryToSaltTgtConverterInvalidValue()

                        query_item_value = query_item_value[cls.QUERY_REGEX_OPERATOR]

                        return f'not {process_key(query_key=item_key, tgt_type_letter="P")}:{query_item_value}'

                    raise MongoQueryToSaltTgtConverterInvalidValue()
                else:
                    return f'{process_key(query_key=item_key)}:{process_value(item_value)}'

            for key, value in data.items():
                if key in cls.QUERY_COMPARISONS_OPERATORS:
                    if not isinstance(value, list):
                        msg = 'Query is invalid'
                        raise ValueError(msg)

                    result_list.append(process_group(group_items=value, group_op=key))
                else:
                    try:
                        result_list.append(process_item(item_key=key, item_value=value))
                    except MongoQueryToSaltTgtConverterUnknownKey:
                        continue

            return f' {cls.QUERY_TO_TGT_CONTAINS_OPERATORS_MAP[comparison_op]} '.join(result_list)

        result: str = process(data=query_dict)

        if result.startswith('( ') and result.endswith(' )'):
            result = result[2:-2]

        return result
