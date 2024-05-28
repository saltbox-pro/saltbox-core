"""
JID — Job ID — is a numeric value to exactly identify jobs in SaltStack.

By default JIDs are monotonically increasing 20-digits values based on datetime.

The module provides handful convertion functions for default datetime-based JID values.
"""

import re

from datetime import datetime, timezone
from typing import Union

JID_FORMAT = '%Y%m%d%H%M%S%f'
# Matches JID in expected format, but does not validate datetime
JID_REGEX = re.compile(
    r'^(?P<year>\d{4})(?P<month>\d{2})(?P<day>\d{2})(?P<hour>\d{2})'
    r'(?P<minute>\d{2})(?P<second>\d{2})(?P<microsecond>\d{6})$'
)


class JidError(RuntimeError):
    ...


class UnexpectedJidFormatError(JidError):
    ...


def jid_from_datetime(value: datetime) -> int:
    """
    Convert datetime object to JID str
    """
    strval = value.strftime(JID_FORMAT)
    return int(strval)


def jid_to_datetime(jid: Union[int, str]) -> datetime:
    """
    Convert JID to UTC aware datetime

    :raises UnexpectedJidFormatError: on missformated JID
    """
    if isinstance(jid, int):
        jid = str(jid).zfill(20)
    # re is more efficient than datatime.strptime
    if not (match := JID_REGEX.match(jid)):
        msg = f'JID must be exclusively 20 digits value, but "{jid}" given'
        raise UnexpectedJidFormatError(msg)

    kwargs = {k: int(val) for k, val in match.groupdict().items()}

    try:
        return datetime(**kwargs, tzinfo=timezone.utc)
    except ValueError as err:
        raise UnexpectedJidFormatError(err)
