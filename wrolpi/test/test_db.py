import mock
import pytest
from sqlalchemy.orm import Session

from wrolpi.db import optional_session
from wrolpi.flags import WROLPiFlag


@pytest.mark.asyncio
async def test_optional_session(test_session):
    """
    `optional_session` wraps a function and provides a session if one was not passed.
    """
    url = test_session.get_bind().url

    called = mock.Mock()

    def check_call(func):
        # Function can be called with various arguments.
        func()
        func(session=test_session)
        func(test_session)
        # Function actually ran.
        called.assert_called()

    @optional_session()
    def sync_with_wrapper(session: Session):
        assert session.get_bind().url == url
        called()

    check_call(sync_with_wrapper)

    # Commit can be passed.
    @optional_session(commit=True)
    def sync_with_commit(session: Session):
        assert session.get_bind().url == url
        called()

    check_call(sync_with_commit)

    # Wrapper is not called.
    @optional_session
    def sync_without_wrapper(session: Session):
        assert session.get_bind().url == url
        called()

    check_call(sync_without_wrapper)

    async def check_async_call(func):
        # Function can be called with various arguments.
        await func()
        await func(session=test_session)
        await func(test_session)
        # Function actually ran.
        called.assert_called()

    # Async is called.
    @optional_session
    async def async_without_wrapper(session: Session):
        assert session.get_bind().url == url
        called()

    await check_async_call(async_without_wrapper)

    # Async is called with wrapper.
    @optional_session(commit=True)
    async def async_with_wrapper(session: Session):
        assert session.get_bind().url == url
        called()

    await check_async_call(async_with_wrapper)


@pytest.mark.asyncio
async def test_optional_session_commit(test_session):
    """It is possible to request that a Commit happens after your wrapped function completes."""
    assert test_session.query(WROLPiFlag).count() == 0

    @optional_session(commit=True)
    async def func(session: Session = None):
        flag = WROLPiFlag(refresh_complete=True)
        session.add(flag)
        # No `session.commit()` here.

    await func()

    assert test_session.query(WROLPiFlag).one().refresh_complete is True
