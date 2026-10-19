import csv
import io
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from saltbox_core.minion_collections.schemas.extra_data_category import ExtraDataCategoryModel
from saltbox_sdk.event_bus.schemas import MinionExtraDataCategoryFieldType
from saltbox_sdk.exceptions import SaltBoxValidationException
from saltbox_sdk.fastapi_utils.csv_export import FORMULA_PREFIXES

CSV_MINION_COLUMNS = ['minion_id', 'master']
CSV_UPDATED_AT_COLUMN = 'updated_at'
CSV_BOOL_VALUES = {'true': True, 'false': False}


@dataclass
class ImportRow:
    row_number: int
    minion_id: str
    master: str
    data: dict[str, Any]


def unescape_csv_value(value: str) -> str:
    if value.startswith("'") and value[1:].startswith(FORMULA_PREFIXES):
        return value[1:]

    return value


def parse_csv_value(value: str, field_type: MinionExtraDataCategoryFieldType | None) -> Any:
    value = unescape_csv_value(value)

    if field_type is None or field_type == MinionExtraDataCategoryFieldType.STR:
        return value
    if field_type == MinionExtraDataCategoryFieldType.INT:
        return int(value)
    if field_type == MinionExtraDataCategoryFieldType.FLOAT:
        return float(value)
    if field_type == MinionExtraDataCategoryFieldType.BOOL:
        if value.lower() not in CSV_BOOL_VALUES:
            raise ValueError(value)
        return CSV_BOOL_VALUES[value.lower()]
    if field_type == MinionExtraDataCategoryFieldType.DATETIME:
        return datetime.fromisoformat(value)
    if field_type in (MinionExtraDataCategoryFieldType.LIST, MinionExtraDataCategoryFieldType.DICT):
        parsed = json.loads(value)
        if not isinstance(parsed, field_type.python_type):
            raise ValueError(value)
        return parsed

    raise ValueError(value)


def get_import_data_columns(category: ExtraDataCategoryModel, header: list[str]) -> list[str]:
    field_types = {field.name: field.type for field in category.fields}

    if header[: len(CSV_MINION_COLUMNS)] != CSV_MINION_COLUMNS:
        msg = f'The first CSV columns must be {", ".join(CSV_MINION_COLUMNS)}'
        raise SaltBoxValidationException(msg)

    data_columns = header[len(CSV_MINION_COLUMNS) :]
    if (
        data_columns
        and data_columns[-1] == CSV_UPDATED_AT_COLUMN
        and (CSV_UPDATED_AT_COLUMN not in field_types or data_columns.count(CSV_UPDATED_AT_COLUMN) > 1)
    ):
        data_columns = data_columns[:-1]

    errors: list[str] = []
    for name in sorted(set(data_columns)):
        if data_columns.count(name) > 1:
            errors.append(f'`{name}`: duplicated column')
        if field_types.get(name) == MinionExtraDataCategoryFieldType.BYTES:
            errors.append(f'`{name}`: bytes fields are not supported in CSV')

    if errors:
        msg = f'Invalid CSV header: {"; ".join(errors)}'
        raise SaltBoxValidationException(msg)

    return data_columns


def parse_import_row_data(
    category: ExtraDataCategoryModel, data_columns: list[str], values: list[str]
) -> tuple[dict[str, Any], list[str]]:
    field_types = {field.name: field.type for field in category.fields}
    data: dict[str, Any] = {}
    errors: list[str] = []

    for name, value in zip(data_columns, values, strict=True):
        if value == '':
            continue
        try:
            data[name] = parse_csv_value(value, field_types.get(name))
        except ValueError:
            errors.append(f'`{name}`: expected {field_types[name]}')

    if errors:
        return data, errors

    if not data:
        return data, ['extra data item must contain at least one field']

    try:
        return category.clean_data(data), []
    except SaltBoxValidationException as error:
        return data, [error.detail]


def parse_import_csv(category: ExtraDataCategoryModel, content: str) -> tuple[list[ImportRow], list[str]]:
    reader = csv.reader(io.StringIO(content))
    header = next(reader, None)
    if header is None:
        msg = 'CSV file is empty'
        raise SaltBoxValidationException(msg)

    data_columns = get_import_data_columns(category, header)
    rows: list[ImportRow] = []
    errors: list[str] = []

    for row_number, row in enumerate(reader, start=2):
        if not any(row):
            continue

        if len(row) != len(header):
            errors.append(f'Row {row_number}: expected {len(header)} columns, got {len(row)}')
            continue

        data_values = row[len(CSV_MINION_COLUMNS) : len(CSV_MINION_COLUMNS) + len(data_columns)]
        data, row_errors = parse_import_row_data(category, data_columns, data_values)
        if row_errors:
            errors.append(f'Row {row_number}: {"; ".join(row_errors)}')
            continue

        rows.append(ImportRow(row_number, unescape_csv_value(row[0]), unescape_csv_value(row[1]), data))

    return rows, errors
