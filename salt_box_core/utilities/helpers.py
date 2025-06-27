import re
from datetime import UTC, datetime
from typing import Any

# 2025-11-14
DATE_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}$')
# 2025-11-14T09:50:38.000+00:00
DATETIME_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}.\d{3}\+\d{2}:\d{2}$')
# 2025-11-14T09:50:38
DATETIME_PATTERN_NO_MS = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$')
# 2025-03-12 00:00:00
DATETIME_PATTERN_NO_TZ = re.compile(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$')
# 2025-04-11T09:00:49.331Z
DATETIME_PATTERN_Z = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$')


def utc_now() -> datetime:
    return datetime.now(UTC)


def get_now_stamp_str() -> str:
    return str(datetime.now(UTC).timestamp())


def datetime_now_sec() -> datetime:
    return datetime.now().astimezone().replace(microsecond=0)


def recursive_replace_dates(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: recursive_replace_dates(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [recursive_replace_dates(item) for item in obj]
    elif isinstance(obj, str) and DATE_PATTERN.match(obj):
        return datetime.strptime(obj, '%Y-%m-%d').replace(tzinfo=UTC)
    elif isinstance(obj, str) and DATETIME_PATTERN.match(obj):
        return datetime.strptime(obj, '%Y-%m-%dT%H:%M:%S.%f%z')
    elif isinstance(obj, str) and DATETIME_PATTERN_NO_MS.match(obj):
        return datetime.strptime(obj, '%Y-%m-%dT%H:%M:%S').replace(tzinfo=UTC)
    elif isinstance(obj, str) and DATETIME_PATTERN_NO_TZ.match(obj):
        return datetime.strptime(obj, '%Y-%m-%d %H:%M:%S').replace(tzinfo=UTC)
    elif isinstance(obj, str) and DATETIME_PATTERN_Z.match(obj):
        return datetime.strptime(obj, '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=UTC)
    else:
        return obj
