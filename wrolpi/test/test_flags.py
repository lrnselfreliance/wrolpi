import asyncio

import pytest
from sqlalchemy.orm import Session

from wrolpi import flags


def assert_db(session: Session, name: str, expected: bool):
    f = session.query(flags.WROLPiFlag).one_or_none()
    if not f:
        raise AssertionError('No flags row in DB!')

    assert getattr(f, name) is expected


def test_flags(async_client, test_session, flags_lock):
    """DB flags can be saved."""
    assert flags.refresh_complete.is_set() is False
    assert not any(v for k, v in flags.get_flags().items())

    flags.refresh_complete.set()
    assert_db(test_session, 'refresh_complete', True)
    assert flags.get_flags()['refresh_complete']

    flags.refresh_complete.clear()
    assert_db(test_session, 'refresh_complete', False)
    assert not any(v for k, v in flags.get_flags().items())


def test_flags_with(async_client, flags_lock):
    """A Flag can be used with `with` context."""
    assert flags.refreshing.is_set() is False, 'Flag should not be set by default'
    assert not any(v for k, v in flags.get_flags().items())

    with flags.refreshing:
        assert flags.refreshing.is_set() is True, 'Flag should be set within context.'
        assert flags.get_flags()['refreshing']

    assert flags.refreshing.is_set() is False, 'Flag should not be restored after context.'
    assert not any(v for k, v in flags.get_flags().items())

    with pytest.raises(ValueError):
        # Can't do two `refreshing` as once.
        with flags.refreshing:
            with flags.refreshing:
                raise Exception('We should not get here!')


@pytest.mark.asyncio
async def test_flag_wait_for(async_client, flags_lock):
    """Wait for throws an error when waiting exceeds timeout."""
    with pytest.raises(TimeoutError):
        async with flags.refreshing.wait_for(timeout=1):
            await asyncio.sleep(2)
