import logging
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Union

import pytz
from sqlalchemy import types

from wrolpi.vars import DATETIME_FORMAT_MS

logger = logging.getLogger(__name__)

TEST_DATETIME: datetime = None


class Seconds(int, Enum):
    minute = 60
    hour = minute * 60
    day = hour * 24
    week = day * 7


def set_test_now(dt: datetime):
    global TEST_DATETIME
    if dt and not dt.tzinfo:
        # Assume any datetime is UTC during testing.
        dt = dt.replace(tzinfo=pytz.UTC)
    TEST_DATETIME = dt
    return dt


def now() -> datetime:
    """Get the current DateTime in the provided timezone.  Timezone aware."""
    global TEST_DATETIME
    if TEST_DATETIME:
        return TEST_DATETIME
    return datetime.now(tz=timezone.utc)


def strftime(dt: datetime) -> str:
    return dt.isoformat()


def strptime(dt: str) -> datetime:
    if isinstance(dt, str) and dt.endswith(' 00:00'):
        # URL decoding removed +
        dt = f'{dt[:26]}+00:00'
    return datetime.fromisoformat(dt).astimezone(pytz.UTC)


def strpdate(dt: str) -> datetime:
    if '-' in dt:
        return datetime.strptime(dt, '%Y-%m-%d').replace(tzinfo=pytz.UTC)

    return datetime.strptime(dt, '%Y%m%d').replace(tzinfo=pytz.UTC)


def strftime_ms(dt: datetime) -> str:
    return dt.strftime(DATETIME_FORMAT_MS)


def strptime_ms(dt: str) -> datetime:
    return datetime.fromisoformat(dt).astimezone(pytz.UTC)


def from_timestamp(timestamp: float) -> datetime:
    return datetime.fromtimestamp(timestamp).astimezone(pytz.UTC)


def seconds_to_timestamp(seconds: Union[int, float]) -> str:
    """Convert an integer into a timestamp string."""
    seconds = int(seconds)
    weeks, seconds = divmod(seconds, Seconds.week)
    days, seconds = divmod(seconds, Seconds.day)
    hours, seconds = divmod(seconds, Seconds.hour)
    minutes, seconds = divmod(seconds, Seconds.minute)
    timestamp = f'{hours:02}:{minutes:02}:{seconds:02}'
    if weeks:
        timestamp = f'{weeks}w {days}d {timestamp}'
    elif days:
        timestamp = f'{days}d {timestamp}'
    return timestamp


def timedelta_to_timestamp(delta: timedelta) -> str:
    """Convert a datetime.timestamp into a timestamp string.

    >>> timedelta_to_timestamp(timedelta(seconds=60))
    '00:01:00'
    >>> timedelta_to_timestamp(timedelta(weeks=1, days=1, seconds=7))
    '1w 1d 00:00:07'
    >>> timedelta_to_timestamp(timedelta(days=10))
    '1w 3d 00:00:00'
    """
    return seconds_to_timestamp(delta.total_seconds())


class TZDateTime(types.TypeDecorator):
    """Forces all datetime to have a timezone.  Stores all datetime in DB as UTC."""
    impl = types.DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if isinstance(value, datetime):
            if not value.tzinfo:
                raise TypeError(f"tzinfo is required: {value}")
            # Store all timestamps as UTC timezone.
            value = value.astimezone(timezone.utc)
        elif isinstance(value, str) and '-' in value:
            value = datetime.fromisoformat(value)
        return value

    def process_result_value(self, value: datetime, dialect):
        if value is not None:
            # Assume the DB timestamp is UTC.
            value = value.replace(tzinfo=pytz.utc) if not value.tzinfo else value
        return value
