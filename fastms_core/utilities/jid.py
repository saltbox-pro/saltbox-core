"""
JID — Job ID — is a numeric value to exactly identify jobs in SaltStack.

By default JIDs are monotonically increasing 20-digits values based on datetime.

The module provides handful convertion functions for default datetime-based JID values.
"""

from __future__ import annotations

import re

from datetime import datetime, timezone

JID_FORMAT = '%Y%m%d%H%M%S%f'
# Matches JID in expected format, but does not validate datetime
JID_REGEX = (
    r'^(?P<year>\d{4})(?P<month>\d{2})(?P<day>\d{2})(?P<hour>\d{2})'
    r'(?P<minute>\d{2})(?P<second>\d{2})(?P<microsecond>\d{6})$'
)
JID_PATTERN = re.compile(JID_REGEX)


class JidError(RuntimeError):
    ...


class UnexpectedJidFormatError(JidError):
    ...


class UnexpectedDataFormatError(JidError):
    ...


# TODO Field type
# TODO class Jid:

def jid_from_datetime(value: datetime) -> int:
    """
    Convert datetime object to JID str
    """
    strval = value.strftime(JID_FORMAT)
    return int(strval)


def jid_to_datetime(jid: int | str) -> datetime:
    """
    Convert JID to UTC aware datetime

    :raises UnexpectedJidFormatError: on missformated JID
    """
    if isinstance(jid, int):
        jid = str(jid).zfill(20)
    # re is more efficient than datatime.strptime
    if not (match := JID_PATTERN.match(jid)):
        msg = f'JID must be exclusively 20 digits value, but "{jid}" given'
        raise UnexpectedJidFormatError(msg)

    kwargs = {k: int(val) for k, val in match.groupdict().items()}

    try:
        return datetime(**kwargs, tzinfo=timezone.utc)
    except ValueError as err:
        raise UnexpectedJidFormatError(err)


# TODO Epoch -> timestamp
def jid_to_epoch(jid: int | str) -> float:
    """
    Get μs-precision POSIX epoch timestamp
    """
    dt = jid_to_datetime(jid)
    return dt.timestamp()


def jid_from_epoch(epoch: float | str) -> int:
    """
    Make JID from μs-precision POSIX epoch timestamp
    """
    # TODO Check epoch precision
    if isinstance(epoch, str):
        try:
            epoch = float(epoch)
        except ValueError as err:
            raise UnexpectedDataFormatError(err)
    dt = datetime.fromtimestamp(epoch, tz=timezone.utc)
    return jid_from_datetime(dt)
