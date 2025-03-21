from datetime import datetime, timedelta, timezone

import pytest
import pytz
from sqlalchemy import Column, Integer

from wrolpi import dates
from wrolpi.common import Base
from wrolpi.dates import TZDateTime, timedelta_to_timestamp, seconds_to_timestamp
from wrolpi.db import get_db_session, get_db_curs
from wrolpi.errors import InvalidDatetime


class TestTable(Base):
    """
    A table for testing purposes.  This should never be in a production database!
    """
    __tablename__ = 'test_table'
    id = Column(Integer, primary_key=True)
    dt = Column(TZDateTime)


def assert_raw_datetime(expected_datetime: str):
    with get_db_curs() as curs:
        curs.execute('SELECT * FROM test_table')
        dt_ = curs.fetchone()['dt']
        assert dt_.isoformat() == expected_datetime


def test_TZDateTime(test_session):
    with get_db_session(commit=True) as session:
        # TZDateTime can be None
        tt = TestTable()
        session.add(tt)
        assert tt.dt is None

    with get_db_session(commit=True) as session:
        tt = session.query(TestTable).one()
        assert tt.dt is None

        # ISO string will be converted.
        tt.dt = '2021-10-05T22:20:10.346823'

    # DB actually contains a UTC timestamp.
    assert_raw_datetime('2021-10-05T22:20:10.346823')

    with get_db_session(commit=True) as session:
        tt = session.query(TestTable).one()
        # Datetime is unchanged.
        assert tt.dt == datetime(2021, 10, 5, 22, 20, 10, 346823, tzinfo=pytz.UTC)

        # Increment by one hour.
        tt.dt += timedelta(seconds=60 * 60)
        assert tt.dt == datetime(2021, 10, 5, 23, 20, 10, 346823, tzinfo=pytz.UTC)

    # DB is incremented by one hour.
    assert_raw_datetime('2021-10-05T23:20:10.346823')


@pytest.mark.parametrize('td,expected', [
    (0, '00:00:00'),
    (1, '00:00:01'),
    (60, '00:01:00'),
    (61, '00:01:01'),
    (65, '00:01:05'),
    (24 * 60 * 60, '1d 00:00:00'),
])
def test_seconds_to_timestamp(td, expected):
    assert seconds_to_timestamp(td) == expected


@pytest.mark.parametrize('td,expected', [
    (timedelta(seconds=0), '00:00:00'),
    (timedelta(seconds=1), '00:00:01'),
    (timedelta(seconds=60), '00:01:00'),
    (timedelta(seconds=61), '00:01:01'),
    (timedelta(seconds=65), '00:01:05'),
    (timedelta(days=1), '1d 00:00:00'),
    (timedelta(seconds=86461), '1d 00:01:01'),
    (timedelta(weeks=1, days=1, seconds=7), '1w 1d 00:00:07'),
    (timedelta(weeks=16, days=3, hours=17, minutes=46, seconds=39), '16w 3d 17:46:39'),
    (timedelta(days=10), '1w 3d 00:00:00'),
    (timedelta(days=10, microseconds=1000), '1w 3d 00:00:00'),
])
def test_timedelta_to_timestamp(td, expected):
    assert timedelta_to_timestamp(td) == expected


@pytest.mark.parametrize('dt,expected', [
    ('20010101', datetime(2001, 1, 1)),
    ('20050607', datetime(2005, 6, 7)),
    ('2006-07-08', datetime(2006, 7, 8)),
    ('2007-8-9', datetime(2007, 8, 9)),
    ('2023-10-19T05:53:24+00:00', datetime(2023, 10, 19, 5, 53, 24, tzinfo=pytz.UTC)),
    ('2022-09-27T00:40:19.000Z', datetime(2022, 9, 27, 0, 40, 19, tzinfo=pytz.UTC)),
    ('06/17/2022', datetime(2022, 6, 17)),
    ('14.3.2002', datetime(2002, 3, 14)),
    ('2002.3.14', datetime(2002, 3, 14)),
    ('2022/8/1', datetime(2022, 8, 1)),
    ('2022-8-1', datetime(2022, 8, 1)),
    ('2023-08-22T02:45:59+0000', datetime(2023, 8, 22, 2, 45, 59, tzinfo=pytz.UTC)),
    ('2023-08-29T15:29-0400', datetime(2023, 8, 29, 15, 29, tzinfo=timezone(timedelta(hours=-4)))),
    ('2023-08-29T15:29+0400', datetime(2023, 8, 29, 15, 29, tzinfo=timezone(timedelta(hours=4)))),
    ('2011-11-04', datetime(2011, 11, 4, 0, 0)),
    ('20111104', datetime(2011, 11, 4, 0, 0)),
    ('2011-11-04T00:05:23', datetime(2011, 11, 4, 0, 5, 23)),
    ('2011-11-04T00:05:23Z', datetime(2011, 11, 4, 0, 5, 23, tzinfo=pytz.UTC)),
    ('20111104T000523', datetime(2011, 11, 4, 0, 5, 23)),
    ('2011-W01-2T00:05:23.283', datetime(2011, 1, 4, 0, 5, 23, 283000)),
    ('2011-11-04 00:05:23.283', datetime(2011, 11, 4, 0, 5, 23, 283000)),
    ('2011-11-04 00:05:23.283+00:00', datetime(2011, 11, 4, 0, 5, 23, 283000, tzinfo=pytz.UTC)),
    ('2011-11-04T00:05:23+04:00', datetime(2011, 11, 3, 20, 5, 23, tzinfo=pytz.UTC)),
    ('2000', datetime(2000, 1, 1, tzinfo=pytz.UTC)),
    ('Tuesday, October 19, 1999 3:41:01 PM', datetime(1999, 10, 19, 15, 41, 1)),
    ('Tue, October 19, 1999 3:41:01 PM', datetime(1999, 10, 19, 15, 41, 1)),
    ('Tue, October 19, 1999 03:41:01 PM', datetime(1999, 10, 19, 15, 41, 1)),
    ('04/27/2024 18:52:55', datetime(2024, 4, 27, 18, 52, 55)),
    ('6/24/2024 6:49:02 PM', datetime(2024, 6, 24, 6, 49, 2)),
    ('2022-02-18T11:00:03.028Z', datetime(2022, 2, 18, 11, 0, 3, 28000, tzinfo=pytz.UTC)),
    # From SingleFile.
    ('Fri Jun 17 2022 19:24:52', datetime(2022, 6, 17, 19, 24, 52)),
    ('9/26/2024 11:55:13 AM', datetime(2024, 9, 26, 11, 55, 13)),
    # PDFs are the Wild West...
    ("D:20221226113758-07'00", datetime(2022, 12, 26, 11, 37, 58, tzinfo=timezone(timedelta(days=-1, seconds=61200)))),
    ('D:20200205184724', datetime(2020, 2, 5, 18, 47, 24)),
    ('D:20091019120104+', datetime(2009, 10, 19, 12, 1, 4)),
])
def test_strpdate(dt, expected):
    assert dates.strpdate(dt) == expected


def test_invalid_strpdate():
    with pytest.raises(InvalidDatetime):
        dates.strpdate('1')
    with pytest.raises(InvalidDatetime):
        dates.strpdate('asdf')
    with pytest.raises(InvalidDatetime):
        dates.strpdate('13/1/2008')

    # Not a real date.
    with pytest.raises(InvalidDatetime):
        dates.strpdate('2001-2-31')
    with pytest.raises(InvalidDatetime):
        dates.strpdate('2001-2-30')

    with pytest.raises(InvalidDatetime):
        dates.strpdate('27/04/2024 18:52:55')
    with pytest.raises(InvalidDatetime):
        dates.strpdate('undefined')
    with pytest.raises(InvalidDatetime):
        dates.strpdate('null')
    with pytest.raises(InvalidDatetime):
        dates.strpdate(None)
