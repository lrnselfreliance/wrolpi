from datetime import datetime, timedelta

from sqlalchemy import Column, Integer

from wrolpi.common import Base
from wrolpi.dates import TZDateTime, local_timezone, strftime_ms
from wrolpi.db import get_db_session, get_db_curs
from wrolpi.test.common import TestAPI, wrap_test_db, skip_circleci


class TestTable(Base):
    """
    A table for testing purposes.  This should never be in a production database!
    """
    __tablename__ = 'test_table'
    id = Column(Integer, primary_key=True)
    dt = Column(TZDateTime)


@skip_circleci
class TestDates(TestAPI):

    def assert_raw_datetime(self, expected_datetime: str):
        with get_db_curs() as curs:
            curs.execute('SELECT * FROM test_table')
            dt_ = curs.fetchone()['dt']
            self.assertEqual(strftime_ms(dt_), expected_datetime)

    @wrap_test_db
    def test_TZDateTime(self):
        with get_db_session(commit=True) as session:
            # TZDateTime can be None
            tt = TestTable()
            session.add(tt)
            self.assertIsNone(tt.dt)

        with get_db_session(commit=True) as session:
            tt = session.query(TestTable).one()
            self.assertIsNone(tt.dt)

            # Store a timezone naive string, it should be assumed this is a local time.
            tt.dt = '2021-10-05 16:20:10.346823'

        # DB actually contains a UTC timestamp.
        self.assert_raw_datetime('2021-10-05 22:20:10.346823')

        with get_db_session(commit=True) as session:
            tt = session.query(TestTable).one()
            # Datetime is unchanged and localized.
            self.assertEqual(tt.dt, local_timezone(datetime(2021, 10, 5, 16, 20, 10, 346823)))

            # Increment by one hour.
            tt.dt += timedelta(seconds=60 * 60)
            self.assertEqual(tt.dt, local_timezone(datetime(2021, 10, 5, 17, 20, 10, 346823)))

        # DB is incremented by one hour.
        self.assert_raw_datetime('2021-10-05 23:20:10.346823')

        with get_db_session(commit=True) as session:
            tt = session.query(TestTable).one()
            # Datetime is incremented by an hour.
            self.assertEqual(tt.dt, local_timezone(datetime(2021, 10, 5, 17, 20, 10, 346823)))
