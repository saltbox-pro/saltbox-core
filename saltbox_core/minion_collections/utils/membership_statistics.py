from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from saltbox_core.minion_collections.schemas.collection_membership import CollectionCountPoint, StatisticsInterval


def sample_times(start: datetime, end: datetime, interval: StatisticsInterval, zone: ZoneInfo) -> list[datetime]:
    start, end = start.astimezone(UTC), end.astimezone(UTC)
    boundary = start.astimezone(zone).replace(minute=0, second=0, microsecond=0)

    if interval != 'hour':
        boundary = boundary.replace(hour=0)
    if interval == 'week':
        boundary -= timedelta(days=boundary.weekday())
    elif interval == 'month':
        boundary = boundary.replace(day=1)

    points = [start]

    while boundary.astimezone(UTC) < end:
        instant = boundary.astimezone(UTC)
        if start < instant < end and instant > points[-1]:
            points.append(instant)
        if interval == 'month':
            if boundary.year == 9999 and boundary.month == 12:
                break
            boundary = boundary.replace(year=boundary.year + boundary.month // 12, month=boundary.month % 12 + 1)
        else:
            step = timedelta(hours=1) if interval == 'hour' else timedelta(days=7 if interval == 'week' else 1)
            base = instant if interval == 'hour' else boundary
            if datetime.max.replace(tzinfo=base.tzinfo) - base < step:
                break
            boundary = (base + step).astimezone(zone)

    if end > start:
        points.append(end)

    return points


def build_points(
    timestamps: list[datetime],
    events: list[tuple[datetime, int]],
    now: datetime,
) -> list[CollectionCountPoint]:
    history_from = events[0][0] if events else None
    points = []
    count = 0
    index = 0

    for timestamp in timestamps:
        while index < len(events) and events[index][0] <= timestamp:
            count += events[index][1]
            index += 1
        known = history_from is not None and history_from <= timestamp <= now
        points.append(CollectionCountPoint(timestamp=timestamp, count=count if known else None))

    return points
