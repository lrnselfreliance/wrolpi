import logging
from datetime import datetime, date, timezone
from enum import Enum

import pytz
from sqlalchemy import types

from wrolpi.errors import InvalidTimezone
from wrolpi.vars import DEFAULT_TIMEZONE_STR, DATETIME_FORMAT, DATETIME_FORMAT_MS

logger = logging.getLogger(__name__)

DEFAULT_TIMEZONE = pytz.timezone(DEFAULT_TIMEZONE_STR)
TEST_DATETIME: datetime = None


class Seconds(int, Enum):
    minute = 60
    hour = minute * 60
    day = hour * 24
    week = day * 7
    year = day * 366


def set_test_now(dt: datetime):
    if dt and not dt.tzinfo:
        dt = local_timezone(dt)
    global TEST_DATETIME
    TEST_DATETIME = dt
    return dt


def set_timezone(tz: pytz.timezone):
    """
    Change the global timezone for WROLPi.  This does NOT save the config.
    """
    global DEFAULT_TIMEZONE

    if not tz:
        raise InvalidTimezone('Timezone cannot be blank!')

    if isinstance(tz, str):
        tz = pytz.timezone(tz)

    logger.info(f'Setting timezone: {tz}')
    DEFAULT_TIMEZONE = tz


def utc_now() -> datetime:
    """
    Get the current DateTime in UTC.  Timezone aware.
    """
    return datetime.utcnow().astimezone(pytz.utc)


def now(tz: pytz.timezone = None) -> datetime:
    """
    Get the current DateTime in the provided timezone.  Timezone aware.
    """
    if TEST_DATETIME:
        return TEST_DATETIME
    tz = tz or DEFAULT_TIMEZONE
    return datetime.utcnow().astimezone(tz)


def local_timezone(dt: datetime) -> datetime:
    """
    Convert the DateTime provided to the local Timezone.  Timezone aware.
    """
    return dt.astimezone(DEFAULT_TIMEZONE)


def today() -> date:
    """
    Return today's date.
    """
    return now().date()


def strftime(dt: datetime) -> str:
    return dt.strftime(DATETIME_FORMAT)


def strptime(dt: str) -> datetime:
    return local_timezone(datetime.strptime(dt, DATETIME_FORMAT))


def strftime_ms(dt: datetime) -> str:
    return dt.strftime(DATETIME_FORMAT_MS)


def strptime_ms(dt: str) -> datetime:
    return local_timezone(datetime.strptime(dt, DATETIME_FORMAT_MS))


def from_timestamp(timestamp: float) -> datetime:
    return local_timezone(datetime.fromtimestamp(timestamp))


class TZDateTime(types.TypeDecorator):
    impl = types.DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if isinstance(value, datetime):
            if not value.tzinfo:
                raise TypeError("tzinfo is required")
            # Store all timestamps as UTC timezone.
            value = value.astimezone(timezone.utc)
        elif isinstance(value, str) and '-' in value:
            value = datetime.fromisoformat(value)
            value = value.astimezone(timezone.utc)
        return value

    def process_result_value(self, value: datetime, dialect):
        if value is not None:
            # Assume the DB timestamp is UTC if not specified.
            value = value.replace(tzinfo=pytz.utc) if not value.tzinfo else value
            value = local_timezone(value)
        return value
