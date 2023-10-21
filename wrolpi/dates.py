import logging
import re
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Union

import dateutil.parser
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


def strpdate(dt: str) -> datetime:
    """
    Attempt to parse a datetime string.  Tries to find a Timezone, if possible.  DB requires timezone.

    TODO replace this in Python 3.11 https://docs.python.org/3/library/datetime.html#datetime.datetime.fromisoformat
    """
    try:
        if dt.count('/') == 2:
            # No timezone info.
            try:
                a, b, c = dt.split('/')
                if len(c) == 4:
                    # Assume m/d/Y
                    return datetime.strptime(dt, '%m/%d/%Y')
                if len(a) == 4:
                    # Y/m/d
                    return datetime.strptime(dt, '%Y/%m/%d')
            except ValueError:
                pass
        elif dt.count('-') == 2 and len(dt) <= 10:
            # No timezone info.
            a, b, c = dt.split('-')
            if len(a) == 4:
                # Y-m-d
                return datetime.strptime(dt, '%Y-%m-%d')

        if dt.startswith('D:'):
            # D:20221226113758-07'00, D:20200205184724, etc.
            dt2 = dt.replace("'", '').rstrip('+')
            try:
                return datetime.strptime(dt2, "D:%Y%m%d%H%M%S%z")
            except ValueError:
                pass

            return datetime.strptime(dt2, "D:%Y%m%d%H%M%S")

        if dt.count('-') == 0 and dt.count('/') == 0 and dt.isdigit() and len(dt) == 8:
            # Assume %Y%m%d date
            return datetime.strptime(dt, '%Y%m%d')

        if dt.count('.') == 2 and len(dt) <= 9:
            # yyyy.mm.dd or dd.mm.yyyy
            try:
                a, b, c = dt.split('.')
                if len(a) == 4:
                    return datetime.strptime(dt, '%Y.%m.%d')
                if len(c) == 4:
                    return datetime.strptime(dt, '%d.%m.%Y')
            except ValueError:
                pass

        try:
            # Fri Jun 17 2022 19:24:52  (from Singlefile)
            return datetime.strptime(dt, '%a %b %d %Y %H:%M:%S')
        except ValueError:
            pass

        if len(dt) == 4 and dt.isdigit():
            # Assume this is a year
            return datetime.strptime(dt, '%Y').replace(tzinfo=pytz.UTC)

        if ',' in dt and (dt.endswith('AM') or dt.endswith('PM')):
            try:
                # Tuesday, October 19, 1999 3:41:01 PM
                return datetime.strptime(dt, '%A, %B %d, %Y %I:%M:%S %p')
            except ValueError:
                pass

            try:
                # Tue, October 19, 1999 3:41:01 PM
                return datetime.strptime(dt, '%a, %B %d, %Y %I:%M:%S %p')
            except ValueError:
                pass

        # Last, try third-party module to parse ISO 8601 datetime.
        return dateutil.parser.isoparse(dt)
    except Exception as e:
        raise RuntimeError(f'Unable to parse datetime string: {dt}') from e


def strftime_ms(dt: datetime) -> str:
    return dt.strftime(DATETIME_FORMAT_MS)


def strptime_ms(dt: str) -> datetime:
    return datetime.fromisoformat(dt).astimezone(pytz.UTC)


def from_timestamp(timestamp: float) -> datetime:
    return datetime.fromtimestamp(timestamp).astimezone(pytz.UTC)


def seconds_to_timestamp(seconds: Union[int, float]) -> str:
    """Convert an integer into a timestamp string.

    >>> seconds_to_timestamp(5)
    # '00:00:05'
    >>> seconds_to_timestamp(60)

    # '00:01:00'
    >>> seconds_to_timestamp(86400)
    # '1d 00:00:00'
    """
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
