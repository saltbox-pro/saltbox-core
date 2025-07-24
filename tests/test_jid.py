from datetime import datetime

import pytest

from saltbox_core.utilities.jid import JID, JidError

TEST_JID = 20240726114145466988
TEST_TIMESTAMP = 1721994105.466988
TEST_DATETIME_STR = '2024-07-26T11:41:45.466988+00:00'
TEST_DATETIME = datetime.fromisoformat(TEST_DATETIME_STR)


def test_valid_jid():
    JID(str(TEST_JID))
    JID(TEST_JID)


def test_invalid_jid():
    with pytest.raises(JidError):
        JID(1)
    with pytest.raises(JidError):
        JID(1234567891011121314151617181920)
    with pytest.raises(JidError):
        JID('123')
    with pytest.raises(JidError):
        JID('ABC')


def test_comparation():
    assert JID(str(TEST_JID)) == JID(TEST_JID)


def test_datetime():
    assert JID(TEST_JID).to_datetime() == TEST_DATETIME


def test_timestamp():
    assert JID(TEST_JID).to_timestamp() == TEST_TIMESTAMP


def test_from_datetim():
    assert JID.from_datetime(TEST_DATETIME) == JID(TEST_JID)


def test_from_timestamp():
    assert JID.from_timestamp(TEST_TIMESTAMP) == JID(TEST_JID)
