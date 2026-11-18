"""A primary WROLPi's database snapshot, for a secondary to copy.

A secondary copies its primary's files with rsync (the daemon of `controller/rsyncd.conf`), and replaces its own
database with the primary's.  A database that is in use cannot be copied as a file, so the secondary first asks the
primary for a snapshot, which the daemon then serves like any other file.  The snapshot is kept between requests: an
unchanged database is not written again, and rsync has the previous copy to compare with.
"""
import asyncio
import pathlib
import shutil
from typing import Optional

from wrolpi import flags
from wrolpi.common import logger, get_media_directory, is_secondary, wrol_mode_enabled
from wrolpi.dates import now
from wrolpi.db import get_db_file
from wrolpi.sync.backup import snapshot_database_if_changed
from wrolpi.sync.status import get_snapshot_status, update_snapshot_status
from wrolpi.vars import PYTEST

logger = logger.getChild(__name__)

# Hidden, so nothing indexes it; inside config, which nothing but the daemon serves.
SNAPSHOT_DIRECTORY = 'config/.sync'
# `snapshot_database` writes a media directory's `config/wrolpi.db`.
SNAPSHOT_PATH = f'{SNAPSHOT_DIRECTORY}/config/wrolpi.db'
# Never fill the drive with a copy of the database; leave this much free.
MIN_FREE_BYTES = 1024 ** 3


def get_snapshot_directory() -> pathlib.Path:
    return get_media_directory() / SNAPSHOT_DIRECTORY


def snapshot_skip_reason() -> Optional[str]:
    """Why a snapshot cannot be made now, or None."""
    if is_secondary():
        return 'A secondary WROLPi is not copied; its primary is'
    if wrol_mode_enabled():
        # Like the backup drive: nothing new is written in WROL Mode.  A snapshot made earlier is still served.
        return 'WROL Mode is enabled'
    if not PYTEST and not flags.db_up.is_set():
        return 'The database is not up'
    try:
        size = get_db_file().stat().st_size
    except FileNotFoundError:
        return 'There is no database'
    # The old snapshot is replaced only after the new one is complete, so both exist for a while.
    if shutil.disk_usage(get_media_directory()).free - size < MIN_FREE_BYTES:
        return 'Not enough free space for a copy of the database'
    return None


def request_snapshot():
    update_snapshot_status(requested=True)


async def run_snapshot() -> dict:
    """Make the snapshot (or keep the one there is, if the database has not changed).  Returns the final status."""
    if reason := snapshot_skip_reason():
        logger.info(f'Not making a database snapshot: {reason}')
        return update_snapshot_status(state='error', finished_at=now().isoformat(), last_error=reason)

    update_snapshot_status(state='running', started_at=now().isoformat(), finished_at=None, last_error=None)
    try:
        written = await asyncio.to_thread(snapshot_database_if_changed, get_snapshot_directory())
        size = (get_media_directory() / SNAPSHOT_PATH).stat().st_size
    except Exception as e:
        logger.error('Failed to make a database snapshot', exc_info=e)
        return update_snapshot_status(state='error', finished_at=now().isoformat(),
                                      last_error=str(e) or type(e).__name__)
    return update_snapshot_status(state='idle', finished_at=now().isoformat(), path=SNAPSHOT_PATH, size=size,
                                  written=written)


async def snapshot_tick():
    """Make a snapshot when one was requested."""
    status = get_snapshot_status()
    if status['state'] == 'running':
        # Only this loop makes snapshots, one at a time: one still marked running when a tick starts was cut off
        # (its process was killed), and would otherwise hold back every later request.
        status = update_snapshot_status(state='error', finished_at=now().isoformat(),
                                        last_error='The snapshot was interrupted')
    if not status['requested']:
        return
    update_snapshot_status(requested=False)
    await run_snapshot()
