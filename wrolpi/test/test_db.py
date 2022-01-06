import pytest
from sqlalchemy.orm import Session

from wrolpi.db import optional_session


def test_optional_session(test_session):
    url = test_session.get_bind().url

    @optional_session()
    def func(session: Session):
        assert session.get_bind().url == url

    func()
    func(session=test_session)

    with pytest.raises(TypeError):
        # keyword must be used.
        func(test_session)
