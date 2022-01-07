from sqlalchemy.orm import Session

from wrolpi.db import optional_session, get_db_session


def test_optional_session(test_session):
    """
    `optional_session` wraps a function and provides a session if one was not passed.
    """
    url = test_session.get_bind().url

    @optional_session()
    def func(session: Session):
        assert session.get_bind().url == url

    func()
    func(session=test_session)
    func(test_session)

    # Commit can be passed.
    @optional_session(commit=True)
    def func(session: Session):
        assert session.get_bind().url == url

    func()
    func(session=test_session)
    func(test_session)

    # Wrapper is not called.
    @optional_session
    def func(session: Session):
        assert session.get_bind().url == url

    func()
    func(session=test_session)
    func(test_session)


def test_test_session_is_required():
    """
    fixture `test_session` must be used in all tests to avoid using the real database.
    """
    try:
        with get_db_session() as session:
            raise Exception('test engine was not used!!')
    except ValueError as e:
        assert 'test database' in str(e)
