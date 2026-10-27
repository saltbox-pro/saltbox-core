from datetime import datetime, timedelta
from typing import Any

from saltbox_core.config import SETTINGS
from saltbox_sdk.exceptions import SaltBoxValidationException
from saltbox_sdk.utilities.helpers import utc_now


def get_minion_active_dt() -> datetime:
    return utc_now().replace(microsecond=0) - timedelta(seconds=SETTINGS.minion_inactive_period)


def parse_bool_filter(field_name: str, value: Any) -> bool:
    if isinstance(value, dict) and len(value) == 1:
        lookup, lookup_value = next(iter(value.items()))

        if lookup in ('$eq', '$ne') and isinstance(lookup_value, bool):
            return lookup_value if lookup == '$eq' else not lookup_value
    elif isinstance(value, bool):
        return value

    msg = f'Field `{field_name}` supports only `$eq` and `$ne` operators with a boolean value'
    raise SaltBoxValidationException(msg)
