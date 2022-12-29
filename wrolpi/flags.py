import multiprocessing
import threading
from typing import List

from sqlalchemy import Column, Boolean, Integer

from wrolpi.common import logger, Base

__all__ = [
    'get_flags',
    'refreshing',
    'refresh_complete',
]

from wrolpi.vars import PYTEST

logger = logger.getChild(__name__)

TESTING_LOCK = multiprocessing.Event()


class Flag:
    """A simple wrapper around multiprocessing.Event.

    This allows synchronization between the App and this API.

    This may store it's value in the DB table wrolpi_flag."""

    def __init__(self, name: str, store_db: bool = False):
        if PYTEST:
            # Use threading Event during testing to avoid tests clobbering each other.
            self._flag = threading.Event()
        else:
            self._flag = multiprocessing.Event()
        self.name = name
        self.store_db = store_db

    def __repr__(self):
        return f'<Flag {repr(self.name)}>'

    def set(self):
        """Set the multiprocessing.Event for this Flag."""
        if PYTEST and not TESTING_LOCK.is_set():
            # Testing, but the test does not need flags.
            return

        self._flag.set()
        self._save(True)

    def clear(self):
        """Clear the multiprocessing.Event for this Flag."""
        if PYTEST and not TESTING_LOCK.is_set():
            # Testing, but the test does not need flags.
            return

        self._flag.clear()
        self._save(False)

    def is_set(self):
        """Return True if this multiprocessing.Event is set."""
        if PYTEST and not TESTING_LOCK.is_set():
            # Testing, but the test does not need flags.
            return

        return self._flag.is_set()

    def __enter__(self):
        if PYTEST and not TESTING_LOCK.is_set():
            # Testing, but the test does not need flags.
            return

        if self._flag.is_set():
            raise ValueError(f'{self} flag is already set!')
        self.set()

    def __exit__(self, exc_type, exc_val, exc_tb):
        if PYTEST and not TESTING_LOCK.is_set():
            # Testing, but the test does not need flags.
            return

        self.clear()

    def _save(self, value):
        if self.store_db:
            from wrolpi.db import get_db_curs
            # Store the value of this Flag in it's matching column in the DB.  Not all flags will do this.
            try:
                with get_db_curs(commit=True) as curs:
                    # Upsert the only row in the table.
                    curs.execute(f'''
                        INSERT INTO wrolpi_flag (id, {self.name}) VALUES (1, %(value)s)
                        ON CONFLICT (id) DO UPDATE SET {self.name} = %(value)s
                        ''', dict(value=value))
            except Exception as e:
                logger.critical(f'Unable to save flag! {repr(self)}', exc_info=e)


# The global refresh is running.
refreshing = Flag('refreshing')
# The global refresh has been performed.  This is False on a fresh instance of WROLPi.
refresh_complete = Flag('refresh_complete', store_db=True)
# Third party packages that may be required.  See `cmd.py`
chromium_installed = Flag('chromium_installed')
ffmpeg_installed = Flag('ffmpeg_installed')
ffprobe_installed = Flag('ffprobe_installed')
nmcli_installed = Flag('nmcli_installed')
readability_installed = Flag('readability_installed')
singlefile_installed = Flag('singlefile_installed')
yt_dlp_installed = Flag('yt_dlp_installed')


def get_flags() -> List[str]:
    """Return a list of all Flags which are set."""
    flags = []
    if refreshing.is_set():
        flags.append('refreshing')
    if refresh_complete.is_set():
        flags.append('refresh_complete')
    if chromium_installed.is_set():
        flags.append('chromium_installed')
    if ffmpeg_installed.is_set():
        flags.append('ffmpeg_installed')
    if ffprobe_installed.is_set():
        flags.append('ffprobe_installed')
    if nmcli_installed.is_set():
        flags.append('nmcli_installed')
    if readability_installed.is_set():
        flags.append('readability_installed')
    if singlefile_installed.is_set():
        flags.append('singlefile_installed')
    if yt_dlp_installed.is_set():
        flags.append('yt_dlp_installed')
    return flags


class WROLPiFlag(Base):
    __tablename__ = 'wrolpi_flag'
    id = Column(Integer, primary_key=True)
    refresh_complete = Column(Boolean, default=False)

    def __repr__(self):
        return f'<WROLPiFlag refresh_complete={self.refresh_complete}>'


def init_flags():
    """Set flags to match their DB values."""
    from wrolpi.db import get_db_session
    with get_db_session() as session:
        flags: WROLPiFlag = session.query(WROLPiFlag).one_or_none()
        if flags:
            if flags.refresh_complete is True:
                refresh_complete.set()
            else:
                refresh_complete.clear()
