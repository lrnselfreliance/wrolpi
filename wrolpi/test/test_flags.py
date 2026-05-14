import asyncio
from pathlib import Path
from unittest import mock

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
    assert flags.file_worker_busy.is_set() is False, 'Flag should not be set by default'
    assert not any(v for k, v in flags.get_flags().items())

    with flags.file_worker_busy:
        assert flags.file_worker_busy.is_set() is True, 'Flag should be set within context.'
        assert flags.get_flags()['file_worker_busy']

    assert flags.file_worker_busy.is_set() is False, 'Flag should not be restored after context.'
    assert not any(v for k, v in flags.get_flags().items())

    with pytest.raises(ValueError):
        # Can't do two `file_worker_busy` as once.
        with flags.file_worker_busy:
            with flags.file_worker_busy:
                raise Exception('We should not get here!')


@pytest.mark.asyncio
async def test_flag_wait_for(async_client, flags_lock):
    """Wait for throws an error when waiting exceeds timeout."""
    with pytest.raises(TimeoutError):
        async with flags.file_worker_busy.wait_for(timeout=1):
            await asyncio.sleep(2)


def _patch_mounts(mounted_paths: set, media_dir: Path):
    """Make Path.is_mount return True only for paths in `mounted_paths`.

    Resolves all paths so test inputs match what the helper sees.
    """
    mounted = {Path(p).resolve() for p in mounted_paths}

    def fake_is_mount(self):
        try:
            return self.resolve() in mounted
        except OSError:
            return False

    return mock.patch.object(Path, 'is_mount', fake_is_mount)


def test_destinations_have_mounted_storage_all_covered_by_root_mount(test_directory, test_wrolpi_config):
    """The single common case: /media/wrolpi itself is mounted, so all destinations are covered."""
    with _patch_mounts({test_directory}, test_directory):
        assert flags._destinations_have_mounted_storage() is True


def test_destinations_have_mounted_storage_nothing_mounted(test_directory, test_wrolpi_config):
    """Fresh install: no mounts at all, warning should fire (returns False)."""
    with _patch_mounts(set(), test_directory):
        assert flags._destinations_have_mounted_storage() is False


def test_destinations_have_mounted_storage_partial_coverage(async_client, test_directory, test_wrolpi_config):
    """If videos is on a drive but archive/zims/map are not, return False.

    This is the SD-card-fill case: archive downloads would still hit root.
    """
    from wrolpi.common import get_wrolpi_config
    # Point videos at a subdirectory that has its own mount.
    get_wrolpi_config().videos_destination = 'one/videos/%(channel_tag)s/%(channel_name)s'
    with _patch_mounts({test_directory / 'one'}, test_directory):
        # videos covered, but archive/zims/map default destinations are not.
        assert flags._destinations_have_mounted_storage() is False


def test_destinations_have_mounted_storage_each_destination_on_its_own_mount(async_client, test_directory, test_wrolpi_config):
    """Multi-drive setup: every destination has its own mount above it. Pass."""
    from wrolpi.common import get_wrolpi_config
    config = get_wrolpi_config()
    config.videos_destination = 'one/videos/%(channel_tag)s/%(channel_name)s'
    config.archive_destination = 'two/archive/%(domain_tag)s/%(domain)s'
    config.zims_destination = 'three/zims'
    config.map_destination = 'four/map'

    mounts = {
        test_directory / 'one',
        test_directory / 'two',
        test_directory / 'three',
        test_directory / 'four',
    }
    with _patch_mounts(mounts, test_directory):
        assert flags._destinations_have_mounted_storage() is True


def test_destinations_have_mounted_storage_template_only_destination(async_client, test_directory, test_wrolpi_config):
    """A destination with no static prefix (just '%(...)s') walks straight up to media_dir."""
    from wrolpi.common import get_wrolpi_config
    get_wrolpi_config().videos_destination = '%(channel_name)s'
    with _patch_mounts({test_directory}, test_directory):
        # Static prefix is empty -> candidate is media_dir itself, which is mounted.
        assert flags._destinations_have_mounted_storage() is True


def test_destinations_have_mounted_storage_docker_mode(test_directory, test_wrolpi_config):
    """In Docker mode, the helper short-circuits to True."""
    with mock.patch('wrolpi.flags.DOCKERIZED', True), _patch_mounts(set(), test_directory):
        assert flags._destinations_have_mounted_storage() is True


def test_destinations_have_mounted_storage_dotdot_escape(async_client, test_directory, test_wrolpi_config):
    """A '..'-relative destination escapes media_dir and must be treated as uncovered.

    Without the resolve+escape check, the walk would terminate at media_dir
    (which is mounted) and incorrectly return True, even though the real
    destination resolves outside the mount and writes to the root filesystem.
    """
    from wrolpi.common import get_wrolpi_config
    get_wrolpi_config().videos_destination = '../outside'
    with _patch_mounts({test_directory}, test_directory):
        assert flags._destinations_have_mounted_storage() is False
