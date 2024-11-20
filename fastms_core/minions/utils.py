from fastapi.exceptions import RequestValidationError

from fastms_core.minions.schemas import GrainsSchema, MinionSchema


def detect_field_type(field_name: str) -> str:
    """Detect field type by field name"""

    if '.' in field_name:
        field_name_chain = field_name.split('.')
        if field_name_chain[0] == 'grains':
            field_type = GrainsSchema.model_fields[field_name_chain[1]].annotation
        else:
            raise RequestValidationError(
                errors=[
                    {
                        'loc': ['field', 'field'],
                        'msg': f'Invalid field: {field_name}',
                        'type': 'value_error',
                        'input': field_name,
                    }
                ]
            )
    else:
        field_type = MinionSchema.model_fields[field_name].annotation
    return str(field_type)


def make_aggregate_sequence(field_name: str) -> list:
    """Create aggregation sequence for grouping unique values for a field"""

    field_type = detect_field_type(field_name)
    # Only grains subfields are supported (validation in schemas.py: MinionFilterValuesQueryParams)
    if 'list' in str(field_type):
        group = [
            {'$unwind': f'${field_name}'},
            {'$group': {'_id': f'${field_name}', 'count': {'$sum': 1}}},
            {'$project': {'value': '$_id', 'count': 1, '_id': 0}},
            {'$sort': {'count': -1}},
        ]
    # FIXME: Bad implementation (especially for `hwaddr_interfaces` field)
    elif 'dict' in str(field_type):
        group = [
            {'$project': {f'{field_name}': 1}},
            {'$unwind': f'${field_name}'},
            {'$group': {'_id': {'k': f'${field_name}', 'v': f'${field_name}'}, 'count': {'$sum': 1}}},
            {'$project': {'value': '$_id.v', 'count': 1, '_id': 0}},
            {'$sort': {'count': -1}},
        ]
    else:
        group = [
            {'$group': {'_id': f'${field_name}', 'count': {'$sum': 1}}},
            {'$project': {'value': '$_id', 'count': 1, '_id': 0}},
            {'$sort': {'count': -1}},
        ]
    return group
