import asyncio
import contextlib
import multiprocessing
from datetime import datetime
from pathlib import Path

from sqlalchemy import Column, Boolean, Integer

from wrolpi.common import logger, Base, get_media_directory, get_wrolpi_config
from wrolpi.vars import DOCKERIZED

__all__ = [
    'get_flags',
    'file_worker_busy',
    'refresh_complete',
]

from wrolpi.vars import PYTEST

logger = logger.getChild(__name__)

TESTING_LOCK = multiprocessing.Event()

FLAG_NAMES = set()


class Flag:
    """A simple wrapper around multiprocessing.Event.

    This allows synchronization between the App and this API.

    This may store its value in the DB table wrolpi_flag."""

    def __init__(self, name: str, store_db: bool = False):
        self.name = name
        self.store_db = store_db
        FLAG_NAMES.add(name)

    def __repr__(self):
        return f'<Flag {repr(self.name)}>'

    def set(self):
        """Set the multiprocessing.Event for this Flag."""
        if PYTEST and not TESTING_LOCK.is_set():
            # Testing, but the test does not need flags.
            return

        from wrolpi.api_utils import api_app
        api_app.shared_ctx.flags.update({self.name: True})
        self._save(True)

    def clear(self):
        """Clear the multiprocessing.Event for this Flag."""
        if PYTEST and not TESTING_LOCK.is_set():
            # Testing, but the test does not need flags.
            return

        from wrolpi.api_utils import api_app
        api_app.shared_ctx.flags.update({self.name: False})
        self._save(False)

    def is_set(self):
        """Return True if this multiprocessing.Event is set."""
        if PYTEST and not TESTING_LOCK.is_set():
            # Testing, but the test does not need flags.
            return

        from wrolpi.api_utils import api_app
        return api_app.shared_ctx.flags[self.name]

    def __enter__(self):
        if PYTEST and not TESTING_LOCK.is_set():
            # Testing, but the test does not need flags.
            return

        if self.is_set():
            raise ValueError(f'{self} flag is already set!')
        self.set()

    def __exit__(self, exc_type, exc_val, exc_tb):
        if PYTEST and not TESTING_LOCK.is_set():
            # Testing, but the test does not need flags.
            return

        self.clear()

    def _save(self, value: bool):
        if self.store_db:
            from wrolpi.db import get_db_session
            # Store the value of this Flag in it's matching column in the DB.  Not all flags will do this.
            try:
                with get_db_session(commit=True) as session:
                    # Upsert the only row in the table.
                    flag_row = session.query(WROLPiFlag).filter_by(id=1).one_or_none()
                    if not flag_row:
                        flag_row = WROLPiFlag(id=1)
                        session.add(flag_row)
                    setattr(flag_row, self.name, value)
            except Exception as e:
                logger.critical(f'Unable to save flag! {repr(self)}', exc_info=e)

    @contextlib.asynccontextmanager
    async def wait_for(self, timeout: int = 0):
        """Wait for this Flag to be set."""
        async with wait_for_flag(self, timeout=timeout):
            yield


# Set by `check_db_is_up`.
db_up = Flag('db_up')
# The database file was written by a NEWER WROLPi than this one (drive moved from another system).
# While set, the database must not be written; upgrade this WROLPi instead.
db_version_mismatch = Flag('db_version_mismatch')
# Outdated Zims need to be removed.
outdated_zims = Flag('outdated_zims', store_db=True)
# Used to disable or enable downloading when Internet is down.
have_internet = Flag('have_internet')
# Every configured destination (videos/archive/zims/map) has a mounted drive at or above it.
# Cleared when at least one destination would write to the unmounted root filesystem.
media_mounted = Flag('media_mounted')

# The FileWorker is busy (refreshing, moving, tagging, or renaming files).
file_worker_busy = Flag('file_worker_busy')
# Steps of FileWorker operations.
file_worker_counting = Flag('file_worker_counting')
file_worker_discovery = Flag('file_worker_discovery')
file_worker_modeling = Flag('file_worker_modeling')
file_worker_indexing = Flag('file_worker_indexing')
file_worker_cleanup = Flag('file_worker_cleanup')

# A global refresh is currently running.
global_refresh_active = Flag('global_refresh_active')

# Map search index is being built.
map_search_building = Flag('map_search_building')

# The global refresh has been performed.  This is False on a fresh instance of WROLPi.
refresh_complete = Flag('refresh_complete', store_db=True)

# Cookies flags for yt-dlp.
cookies_exist = Flag('cookies_exist')
cookies_unlocked = Flag('cookies_unlocked')


def get_flags() -> dict:
    """Return a list of all Flags which are set."""
    flags = dict(
        cookies_exist=cookies_exist.is_set(),
        cookies_unlocked=cookies_unlocked.is_set(),
        db_up=db_up.is_set(),
        file_worker_busy=file_worker_busy.is_set(),
        file_worker_cleanup=file_worker_cleanup.is_set(),
        file_worker_counting=file_worker_counting.is_set(),
        file_worker_discovery=file_worker_discovery.is_set(),
        file_worker_indexing=file_worker_indexing.is_set(),
        file_worker_modeling=file_worker_modeling.is_set(),
        global_refresh_active=global_refresh_active.is_set(),
        have_internet=have_internet.is_set(),
        map_search_building=map_search_building.is_set(),
        media_mounted=media_mounted.is_set(),
        outdated_zims=outdated_zims.is_set(),
        refresh_complete=refresh_complete.is_set(),
    )
    return flags


class WROLPiFlag(Base):
    __tablename__ = 'wrolpi_flag'
    id = Column(Integer, primary_key=True)
    refresh_complete = Column(Boolean, default=False)
    outdated_zims = Column(Boolean, default=False)

    def __repr__(self):
        return f'<WROLPiFlag' \
               f' refresh_complete={self.refresh_complete}' \
               f' outdated_zims={self.outdated_zims}>'


def _destinations_have_mounted_storage() -> bool:
    """True when every configured destination is backed by a mounted drive.

    Walks each destination (videos/archive/zims/map) from its static path
    prefix up through the media directory; if any ancestor in that range is
    a mount point, the destination is considered covered.  All destinations
    must be covered for this to return True — otherwise a download could
    silently write to the SD card on a Raspberry Pi.

    Docker mode is exempt: the media directory is always a bind mount and
    the user cannot remount drives from inside the container.
    """
    if DOCKERIZED:
        return True

    media_dir = get_media_directory().resolve()

    config = get_wrolpi_config()
    destinations = [
        config.videos_destination,
        config.archive_destination,
        config.zims_destination,
        config.map_destination,
    ]

    for dest in destinations:
        if not dest:
            continue
        # Templated paths like 'videos/%(channel_tag)s/...' can't be fully
        # resolved without a real channel; use the static prefix.
        static_prefix = dest.split('%', 1)[0].rstrip('/')
        candidate = (media_dir / static_prefix) if static_prefix else media_dir
        # Resolve to normalize '..' segments before the walk; otherwise a
        # destination like '../outside' would still walk back through
        # media_dir and falsely report covered.
        candidate = candidate.resolve()

        # If the destination escapes the media directory entirely, the
        # download would land outside any drive we control — treat as
        # uncovered so the warning fires.
        if candidate != media_dir and media_dir not in candidate.parents:
            return False

        covered = False
        cursor = candidate
        while True:
            try:
                if cursor.is_mount():
                    covered = True
                    break
            except OSError:
                # Path doesn't exist yet (e.g. fresh install); keep walking.
                pass
            if cursor == media_dir:
                break
            cursor = cursor.parent
        if not covered:
            return False

    return True


def check_db_is_up():
    """Checks that the database file exists and is initialized, sets flags.db_up if so.

    The database lives inside the media directory, so "DB down" usually means the media drive
    is not mounted (or the DB has not been created/migrated yet)."""
    import sqlite3
    from wrolpi.db import get_db_file
    from wrolpi.db_bootstrap import media_directory_is_unmounted_production

    try:
        if media_directory_is_unmounted_production():
            # Any DB file at the media path is a root-filesystem shadow, not the real database.
            db_up.clear()
            return
        db_file = get_db_file()
        if not db_file.is_file() or db_version_mismatch.is_set():
            db_up.clear()
            return
        # Read-only URI probe; a plain connect would create an empty database file.
        with contextlib.closing(sqlite3.connect(f'file:{db_file}?mode=ro', uri=True)) as conn:
            conn.execute('SELECT version_num FROM alembic_version').fetchone()
        # If we get here, the database is up!
        db_up.set()
    except Exception as e:
        logger.debug(f'DB is not up', exc_info=e)
        db_up.clear()


def init_flags():
    """Read flag values from the DB, copy them to the shared context flags."""
    if not db_up.is_set():
        logger.error(f'Refusing to initialize flags when DB is not up.')
        return

    from wrolpi.api_utils import api_app
    if api_app.shared_ctx.flags_initialized.is_set():
        # Only need to read from once DB at startup.
        return
    api_app.shared_ctx.flags_initialized.set()

    logger.debug('Initializing flags...')

    from wrolpi.db import get_db_session
    with get_db_session() as session:
        flags: WROLPiFlag = session.query(WROLPiFlag).one_or_none()
        if flags:
            if flags.refresh_complete is True:
                refresh_complete.set()
            else:
                refresh_complete.clear()
            if flags.outdated_zims is True:
                outdated_zims.set()
            else:
                outdated_zims.clear()

    # Initialize cookies flags from cookies module state.
    from modules.videos.cookies import cookies_exist as check_cookies_exist, cookies_unlocked as check_cookies_unlocked
    if check_cookies_exist():
        cookies_exist.set()
    if check_cookies_unlocked():
        cookies_unlocked.set()

    logger.debug('Initialized flags')


@contextlib.asynccontextmanager
async def wait_for_flag(flag: Flag, timeout: int = 0):
    """Sleeps until the provided Flag is set.

    >>> async with wait_for_flag(db_up):
    >>>     do_db_operation()

    @raise TimeoutError: Raises this when the timeout is reached.
    """
    start = datetime.now()
    while True:
        if timeout and (elapsed := (datetime.now() - start).total_seconds()) > timeout:
            raise TimeoutError(f'Waited too long ({elapsed}s) for {flag} to be set!')

        if flag.is_set():
            break
        await asyncio.sleep(0.1)

    yield
