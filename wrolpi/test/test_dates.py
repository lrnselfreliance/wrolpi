from sqlalchemy import Column, Integer

from wrolpi.common import Base
from wrolpi.dates import TZDateTime
from wrolpi.db import get_db_session
from wrolpi.test.common import TestAPI, wrap_test_db


class TestTable(Base):
    """
    A table for testing purposes.  This should never be in a production database!
    """
    __tablename__ = 'test_table'
    id = Column(Integer, primary_key=True)
    dt = Column(TZDateTime)


class TestDates(TestAPI):

    @wrap_test_db
    def test_TZDateTime(self):
        with get_db_session(commit=True) as session:
            # TZDateTime can be None
            session.add(TestTable())

        with get_db_session(commit=True) as session:
            tt = session.query(TestTable).one()
            self.assertIsNone(tt.dt)

            # Store a timezone naive string, it should be assumed this is a local time.
            tt.dt = '2021-10-05 16:20:10.346823'

        with get_db_session(commit=True) as session:
            tt = session.query(TestTable).one()
            self.assertEqual(str(tt.dt), '2021-10-05 16:20:10.346823-06:00')

            # Store a timezone string.
            tt.dt = '2021-10-05 00:20:10.346824-08:00'

        with get_db_session() as session:
            tt = session.query(TestTable).one()
            # Timezone is preserved.
            self.assertEqual(str(tt.dt), '2021-10-05 08:20:10.346824-06:00')
