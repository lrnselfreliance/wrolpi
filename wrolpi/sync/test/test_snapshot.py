import contextlib
import shutil
import sqlite3
from collections import namedtuple
from http import HTTPStatus

import pytest

from wrolpi.common import enable_wrol_mode
from wrolpi.db import get_db_file
from wrolpi.sync import backup, snapshot
from wrolpi.sync.status import get_snapshot_status


@pytest.mark.asyncio
async def test_info_says_what_a_secondary_must_check(async_client, test_session, test_wrolpi_config):
    """Before a secondary replaces its database with its primary's, it must know the primary's migration and that the
    primary's media directory is really there."""
    request, response = await async_client.get('/api/sync/info')
    assert response.status_code == HTTPStatus.OK
    assert 'database_revision' in response.json
    assert response.json['media_mounted'] in (True, False)


@pytest.mark.asyncio
async def test_snapshot(async_client, test_session, test_directory, test_wrolpi_config):
    """A requested snapshot is a complete database where the rsync daemon serves it, and an unchanged database is
    not written again."""
    with contextlib.closing(sqlite3.connect(get_db_file())) as live:
        live.execute('CREATE TABLE snapshot_test (name TEXT)')
        live.execute("INSERT INTO snapshot_test VALUES ('one')")
        live.commit()

    request, response = await async_client.post('/api/sync/snapshot')
    assert response.status_code == HTTPStatus.ACCEPTED
    assert get_snapshot_status()['requested'] is True
    assert not (test_directory / snapshot.SNAPSHOT_PATH).exists(), 'made by the perpetual process, not the request'

    await snapshot.snapshot_tick()

    status = get_snapshot_status()
    assert status['state'] == 'idle' and status['last_error'] is None and status['requested'] is False
    assert status['path'] == 'config/.sync/config/wrolpi.db' and status['written'] is True
    copy = test_directory / status['path']
    assert status['size'] == copy.stat().st_size > 0
    with contextlib.closing(sqlite3.connect(f'file:{copy}?mode=ro', uri=True)) as connection:
        assert connection.execute('SELECT name FROM snapshot_test').fetchall() == [('one',)]

    request, response = await async_client.get('/api/sync/status')
    assert response.json['snapshot']['path'] == status['path']

    # Nothing asked for: nothing made.
    modified = copy.stat().st_mtime_ns
    await snapshot.snapshot_tick()
    assert copy.stat().st_mtime_ns == modified

    # Asked again with the database unchanged: the snapshot there is kept.
    snapshot.request_snapshot()
    await snapshot.snapshot_tick()
    assert get_snapshot_status()['written'] is False and get_snapshot_status()['state'] == 'idle'
    assert copy.stat().st_mtime_ns == modified

    # The database changed: written again.
    with contextlib.closing(sqlite3.connect(get_db_file())) as live:
        live.execute("INSERT INTO snapshot_test VALUES ('two')")
        live.commit()
    snapshot.request_snapshot()
    await snapshot.snapshot_tick()
    assert get_snapshot_status()['written'] is True
    with contextlib.closing(sqlite3.connect(f'file:{copy}?mode=ro', uri=True)) as connection:
        assert connection.execute('SELECT count(*) FROM snapshot_test').fetchone() == (2,)


@pytest.mark.asyncio
async def test_snapshot_refused(async_client, test_session, test_directory, test_wrolpi_config, make_secondary,
                                monkeypatch):
    """No snapshot is made when it would fill the drive, or on a secondary (which nothing copies)."""
    usage = namedtuple('usage', 'total used free')
    monkeypatch.setattr(snapshot.shutil, 'disk_usage', lambda _: usage(10, 10, snapshot.MIN_FREE_BYTES))
    request, response = await async_client.post('/api/sync/snapshot')
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'free space' in response.json['error']
    # The space ran out between the request and the snapshot.
    snapshot.request_snapshot()
    await snapshot.snapshot_tick()
    assert get_snapshot_status()['state'] == 'error' and 'free space' in get_snapshot_status()['last_error']
    assert not (test_directory / snapshot.SNAPSHOT_PATH).exists()
    monkeypatch.setattr(snapshot.shutil, 'disk_usage', shutil.disk_usage)

    make_secondary('https://primary.example')
    request, response = await async_client.post('/api/sync/snapshot')
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert not get_snapshot_status()['requested']


@pytest.mark.asyncio
async def test_snapshot_refused_in_wrol_mode(async_client, test_session, test_directory, test_wrolpi_config):
    """WROL Mode writes nothing new: no snapshot is made, whether it is asked for now or was asked for before."""
    snapshot.request_snapshot()
    enable_wrol_mode()

    request, response = await async_client.post('/api/sync/snapshot')
    assert response.status_code == HTTPStatus.BAD_REQUEST and 'WROL Mode' in response.json['error']

    await snapshot.snapshot_tick()
    assert get_snapshot_status()['state'] == 'error' and 'WROL Mode' in get_snapshot_status()['last_error']
    assert not (test_directory / snapshot.SNAPSHOT_PATH).exists()


def test_backup_drive_does_not_copy_the_snapshot(test_directory, tmp_path):
    """The backup drive gets its own snapshot; the one kept for secondaries is not copied to it as well."""
    command = backup.build_rsync_command(test_directory, tmp_path)
    assert f'--exclude=/{snapshot.SNAPSHOT_DIRECTORY}/' in command
