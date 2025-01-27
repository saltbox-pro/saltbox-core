from datetime import UTC, datetime


def get_now_stamp_str() -> str:
    return str(datetime.now(UTC).timestamp())


def datetime_now_sec() -> datetime:
    return datetime.now().astimezone().replace(microsecond=0)
