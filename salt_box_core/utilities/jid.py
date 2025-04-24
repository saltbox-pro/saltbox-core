"""
JID — Job ID — is a numeric value to exactly identify jobs in SaltStack.

By default JIDs are monotonically increasing 20-digits values based on datetime.

The module provides handful convertion functions for default datetime-based JID values.
"""

from __future__ import annotations

import functools
import re
from datetime import UTC, datetime


class JidError(RuntimeError): ...


class UnexpectedJidFormatError(JidError): ...


class UnexpectedDataFormatError(JidError): ...


@functools.total_ordering
class JID:
    """
    Represents SaltStack 20-digit Job IDentifier

    By default SaltStack JID contains μs-precision datetime info. Such format is expected.
    """

    LOWER_BOUND = int(1970e16)
    UPPER_BOUND = int(1e20)
    JID_FORMAT = '%Y%m%d%H%M%S%f'
    # Matches JID in expected format, but does not validate datetime
    JID_REGEX = (
        r'^(?P<year>\d{4})(?P<month>\d{2})(?P<day>\d{2})(?P<hour>\d{2})'
        r'(?P<minute>\d{2})(?P<second>\d{2})(?P<microsecond>\d{6})$'
    )
    JID_PATTERN = re.compile(JID_REGEX)

    def __init__(self, jid: int | str) -> None:
        """
        :raises UnexpectedJidFormatError: on invalid or missformated JID
        """
        # re is more efficient than datatime.strptime
        if not (match := self.JID_PATTERN.match(str(jid))):
            msg = f'Jid "{jid}" is not a 20-digits value'
            raise UnexpectedJidFormatError(msg)
        kwargs = {k: int(val) for k, val in match.groupdict().items()}
        try:
            self._datetime = datetime(**kwargs, tzinfo=UTC)
        except ValueError as err:
            raise UnexpectedJidFormatError(err) from err

        if isinstance(jid, str):
            try:
                jid = int(jid)
            except ValueError as err:
                raise UnexpectedJidFormatError(err) from err
        self._value = jid
        if not self._value > self.LOWER_BOUND or not self._value < self.UPPER_BOUND:
            msg = f'"{jid}" is out of bounds'
            raise UnexpectedJidFormatError(msg)

    def __str__(self) -> str:
        return str(self._value).zfill(20)

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}({self._value})'

    def __int__(self) -> int:
        return self._value

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, JID):
            msg = 'Can compare JID only with JID'
            raise TypeError(msg)
        return self._value == other._value

    def __gt__(self, other: JID) -> bool:
        return self._value > other._value

    @classmethod
    def from_datetime(cls, value: datetime) -> JID:
        """
        Make JID from datetime object
        """
        strval = value.strftime(cls.JID_FORMAT)
        return cls(strval)

    @classmethod
    def from_timestamp(cls, epoch: float | str) -> JID:
        """
        Make JID from μs-precision POSIX epoch timestamp
        """
        if isinstance(epoch, str):
            try:
                epoch = float(epoch)
            except ValueError as err:
                raise UnexpectedDataFormatError(err) from err
        dt = datetime.fromtimestamp(epoch, tz=UTC)
        return cls.from_datetime(dt)

    @classmethod
    def generate(cls) -> JID:
        """
        Generate new JID
        """
        return cls.from_datetime(datetime.now(UTC))

    def to_datetime(self) -> datetime:
        """
        Convert JID to UTC aware datetime
        """
        return self._datetime

    def to_timestamp(self) -> float:
        """
        Get μs-precision POSIX epoch timestamp
        """
        dt = self.to_datetime()
        return dt.timestamp()
