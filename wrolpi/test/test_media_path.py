import pytest
from sqlalchemy import Column
from sqlalchemy.exc import StatementError

from wrolpi.common import ModelHelper, Base
from wrolpi.media_path import MediaPathType


class TestTable(Base, ModelHelper):
    __tablename__ = 'testtable'
    path = Column(MediaPathType, primary_key=True)


def test_media_path_type(test_session, test_directory):
    """MediaPathType checks that paths are valid.  They must be in the media directory, absolute, and not empty."""
    # A NULL media path is ok.
    foo = TestTable()
    test_session.commit()

    # The correct media path is in the media directory, and absolute.
    foo.path = test_directory / 'foo'
    test_session.add(foo)
    test_session.commit()

    # The path cannot be empty.
    foo.path = ''
    with pytest.raises(StatementError) as error:
        test_session.commit()
    assert 'cannot be empty' in str(error)
    test_session.rollback()

    # Paths must be strings or Path.
    foo.path = 1
    with pytest.raises(StatementError) as error:
        test_session.commit()
    assert 'Invalid MediaPath type' in str(error)
