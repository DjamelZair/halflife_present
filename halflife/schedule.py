"""When a brief lands. The job runs in the evening, the push arrives the next morning, Dutch time.

GitHub can start a scheduled job hours late, I have seen 10 hours. So the delivery day depends on the
time of day: from noon on the brief is for tomorrow, before noon a late run still counts for this morning.
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from halflife import config

TZ = ZoneInfo(config.PUSH_TIMEZONE)


def delivery_day(now: datetime | None = None) -> date:
    local = (now or datetime.now(TZ)).astimezone(TZ)
    return local.date() + timedelta(days=1) if local.hour >= 12 else local.date()


def push_time(day: date) -> datetime:
    # a zone aware time, so summer and winter time are handled for me
    return datetime.combine(day, time(config.PUSH_HOUR, config.PUSH_MINUTE), tzinfo=TZ)
