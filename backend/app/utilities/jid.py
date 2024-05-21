import re

from datetime import datetime
from typing import Union

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
    return int("{:%Y%m%d%H%M%S%f}".format(value))


def jid_to_datetime(jid: Union[int, str]) -> datetime:
    """
    Convert JID to unawared datetime

    :raises UnexpectedJidFormatError: on missformated JID
    """
    if isinstance(jid, int):
        jid = str(jid).zfill(20)
    if not (match := JID_REGEX.match(jid)):
        raise UnexpectedJidFormatError(
            f'JID must be exclusively 20 digits value, but "{jid}" given')

    kwargs = {k: int(val) for k, val in match.groupdict().items()}

    try:
        return datetime(**kwargs, tzinfo=None)
    except ValueError as err:
        raise UnexpectedJidFormatError(err)
