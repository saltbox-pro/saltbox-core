from datetime import UTC, datetime


def get_now_stamp_str():
    return str(datetime.now(UTC).timestamp())
