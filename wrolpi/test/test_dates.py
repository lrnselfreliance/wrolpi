from datetime import datetime, timedelta

import pytest
import pytz
from sqlalchemy import Column, Integer

from wrolpi.common import Base
from wrolpi.dates import TZDateTime, timedelta_to_timestamp
from wrolpi.db import get_db_session, get_db_curs


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
