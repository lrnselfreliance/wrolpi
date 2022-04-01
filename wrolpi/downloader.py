import asyncio
import multiprocessing
import pathlib
import subprocess
from collections import defaultdict
from datetime import timedelta, datetime
from enum import Enum
from functools import partial
from operator import attrgetter
from typing import List, Optional, Tuple, Dict

from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from wrolpi.common import Base, ModelHelper, logger, iterify, wrol_mode_check, zig_zag
from wrolpi.dates import TZDateTime, now, Seconds, local_timezone, recursive_replace_tz
from wrolpi.db import get_db_session, get_db_curs, get_db_context, optional_session
from wrolpi.errors import InvalidDownload, UnrecoverableDownloadError
from wrolpi.vars import PYTEST

logger = logger.getChild(__name__)

DOWNLOAD_IN_PROGRESS = multiprocessing.Semaphore()
DEFAULT_RETRY_FREQUENCY = timedelta(hours=1)


class DownloadFrequency(int, Enum):
    hourly = 3600
    daily = 86400
    weekly = 604800
    biweekly = 1209600
    days30 = 2592000
    days90 = 7776000


class Download(ModelHelper, Base):
    """
    Model that is used to schedule downloads.
    """
    __tablename__ = 'download'
    id = Column(Integer, primary_key=True)
    url = Column(String, nullable=False)

    attempts = Column(Integer, default=0)
    frequency = Column(Integer)
    last_successful_download = Column(TZDateTime)
    next_download = Column(TZDateTime)
    status = Column(String, default='new')
    info_json = Column(JSONB)
    downloader = Column(Text)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.manager: DownloadManager = None

    def __repr__(self):
        if self.next_download or self.frequency:
            return f'<Download id={self.id} status={self.status} url={repr(self.url)} ' \
                   f'next_download={self.next_download} frequency={self.frequency} attempts={self.attempts}>'
        return f'<Download id={self.id} status={self.status} url={repr(self.url)} attempts={self.attempts}>'

    def __json__(self):
        d = dict(
            downloader=self.downloader,
            frequency=self.frequency,
            id=self.id,
            last_successful_download=self.last_successful_download,
            next_download=self.next_download,
            status=self.status,
            url=self.url,
        )
        return d

    def renew(self, reset_attempts: bool = False):
        """
        Mark this Download as "new" so it will be retried.
        """
        self.status = 'new'
        if reset_attempts:
            self.attempts = 0

    def defer(self):
        """
        Download should be tried again after a time.
        """
        self.status = 'deferred'

    def fail(self):
        """
        Download should not be attempted again.  A recurring Download will raise an error.
        """
        if self.frequency:
            raise ValueError('Recurring download should not be failed.')
        self.status = 'failed'

    def started(self):
        """
        Mark this Download as in progress.
        """
        self.attempts += 1
        self.status = 'pending'

    def complete(self):
        """
        Mark this Download as successfully downloaded.
        """
        self.status = 'complete'
        self.last_successful_download = now()

    def get_downloader(self):
        if self.downloader:
            return self.manager.get_downloader_by_name(self.downloader)

        return self.manager.get_downloader(self.url)


class Downloader:
    name = None
    pretty_name = None
    listable = True

    def __init__(self, priority: int = 50, name: str = None):
        """
        Lower `priority` means the downloader will be checked first.  Valid priority: 0-100

        Downloaders of equal priority will be used at random.
        """
        if not name and not self.name:
            raise NotImplementedError('Downloader must have a name!')
        if not 0 <= priority <= 100:
            raise ValueError(f'Priority of {priority} of {self} is invalid!')

        self.name = self.name or name
        self.priority = priority
        self._kill = multiprocessing.Event()

        self._manager: DownloadManager = None  # noqa

        download_manager.register_downloader(self)

    def __json__(self):
        return dict(name=self.name, pretty_name=self.pretty_name)

    @classmethod
    def valid_url(cls, url) -> Tuple[bool, Optional[dict]]:
        raise NotImplementedError()

    def do_download(self, download: Download):
        raise NotImplementedError()

    @property
    def manager(self):
        if self._manager is None:
            raise NotImplementedError('This needs to be registered, see DownloadManager.register_downloader')
        return self._manager

    @manager.setter
    def manager(self, value):
        self._manager = value

    def kill(self):
        """
        Kill the running download for this Downloader.
        """
        if not self._kill.is_set():
            self._kill.set()

    def clear(self):
        """
        Clear any "kill" request for this Downloader.
        """
        if self._kill.is_set():
            self._kill.clear()

    def process_runner(self, url: str, cmd: List[str], cwd: pathlib.Path, **kwargs) -> int:
        """
        Run a subprocess using the provided arguments.  This process can be killed by the Download Manager.
        """
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd, **kwargs)
        pid = proc.pid
        logger.debug(f'{self} launched download process {pid=} for {url}')

        try:
            while True:
                try:
                    proc.wait(timeout=1.0)
                    # Download finished.
                    break
                except subprocess.TimeoutExpired:
                    pass

                if self._kill.is_set():
                    logger.warning(f'Killing download {pid=}')
                    proc.kill()
                    proc.poll()
                    raise UnrecoverableDownloadError(f'Download {pid=} was killed!')
        finally:
            self._kill.clear()

            # Output all logs from the process.
            # TODO is there a way to stream this output while the process is running?
            logger.debug(f'Download exited with {proc.returncode}')
            outs, errs = proc.communicate()
            for line in outs.decode().splitlines():  # noqa
                logger.debug(line)
            for line in errs.decode().splitlines():  # noqa
                logger.error(line)

        return proc.returncode


class DownloadManager:
    priority_sorter = partial(sorted, key=attrgetter('priority'))

    def __init__(self):
        self.instances = tuple()
        self._instances = dict()
        self.disabled = multiprocessing.Event()

    def register_downloader(self, instance: Downloader):
        if not isinstance(instance, Downloader):
            raise ValueError(f'Invalid downloader cannot be registered! {instance=}')
        if instance in self.instances:
            raise ValueError(f'Downloader already registered! {instance=}')

        instance.manager = self

        i = (*self.instances, instance)
        self.instances = tuple(self.priority_sorter(i))
        self._instances[instance.name] = instance

    def get_downloader(self, url: str) -> Tuple[Downloader, Dict]:
        for i in self.instances:
            result = i.valid_url(url)
            valid, info = result
            if valid:
                return i, info
        raise InvalidDownload(f'Invalid URL {url=}')

    def get_downloader_by_name(self, name: str) -> Downloader:
        """
        Attempts to find a registered Downloader by its name.  Returns None if it cannot be found.
        """
        return self._instances.get(name)

    def get_new_downloads(self, session: Session) -> List[Download]:
        """
        Get all "new" downloads.  This method fetches the first download each iteration, so it will fetch downloads
        that were created after calling it.
        """
        last = None
        while True:
            download = session.query(Download).filter_by(status='new').order_by(Download.id).first()
            if not download:
                return
            if download == last:
                # Got the last download again.  Is something wrong?
                return
            last = download
            download.manager = self
            yield download

    def get_or_create_download(self, url: str, session: Session) -> Download:
        """
        Get a Download by its URL, if it cannot be found create one.
        """
        download = self.get_download(session, url=url)
        if not download:
            download = Download(url=url, status='new')
            session.add(download)
            session.flush()
        download.manager = self
        return download

    def create_download(self, url: str, session, downloader: str = None, skip_download: bool = False,
                        reset_attempts: bool = False) -> Download:
        """
        Schedule a URL for download.  If the URL failed previously, it may be retried.
        """
        downloads = self.create_downloads([url], session, downloader, skip_download=skip_download,
                                          reset_attempts=reset_attempts)
        return downloads[0]

    def create_downloads(self, urls: List[str], session: Session = None, downloader: str = None,
                         skip_download: bool = False, reset_attempts: bool = False) -> List[Download]:
        """
        Schedule all URLs for download.  If one cannot be downloaded, none will be added.
        """
        if not session:
            _, session = get_db_context()

        downloads = []
        forced_downloader = self.get_downloader_by_name(downloader) if downloader else None
        if downloader and not forced_downloader:
            # Could not find the downloader
            raise InvalidDownload(f'Unknown downloader {downloader}')

        with session.transaction:
            for url in urls:
                info_json = None
                downloader = forced_downloader
                if not forced_downloader:
                    # User has requested automatic downloader selection, try and find it.
                    downloader, info_json = self.get_downloader(url)

                download = self.get_or_create_download(url, session)
                # Download may have failed, try again.
                download.renew(reset_attempts=reset_attempts)
                download.downloader = downloader.name
                download.info_json = info_json
                downloads.append(download)

        if skip_download is True:
            return downloads

        if PYTEST:
            # Download now (for testing).
            self._do_downloads(session)
        else:
            # Start downloading ASAP.
            self.start_downloads()

        return downloads

    @wrol_mode_check
    @optional_session
    def _do_downloads(self, session=None):
        """
        This method calls the Downloader's do_download method.
        """
        # This is a long-running function, lets get a session that can be used for a long time.
        if self.disabled.is_set():
            raise InvalidDownload('DownloadManager is disabled')

        try:
            downloads = self.get_new_downloads(session)

            download_count = 0
            for download in downloads:
                if self.disabled.is_set():
                    raise InvalidDownload('DownloadManager is disabled')

                download_count += 1
                download_id = download.id
                url = download.url

                downloader = self.get_downloader_by_name(download.downloader)
                if not downloader:
                    downloader, info_json = self.get_downloader(download.url)
                    download.downloader = downloader.name
                    download.info_json = info_json
                downloader.clear()

                download.started()
                session.commit()

                success = True
                failure = None
                try:
                    success = downloader.do_download(download)
                except UnrecoverableDownloadError as e:
                    # Download failed and should not be retried.
                    logger.warning(f'UnrecoverableDownloadError for {download.url}', exc_info=e)
                    failure = True
                except Exception as e:
                    logger.warning(f'Failed to download {url}.  Will be tried again later.', exc_info=e)

                # Long-running, get the download again.
                with get_db_session(commit=True) as session_:
                    download = self.get_download(session_, id_=download_id)
                    if failure:
                        download.fail()
                    elif success:
                        download.complete()
                        download.next_download = self.get_next_download(download, session)
                    else:
                        download.defer()
                        download.next_download = self.get_next_download(download, session)
                    session_.commit()

            if download_count:
                logger.info(f'Done doing {download_count} downloads.')
        finally:
            session.close()

    def do_downloads_sync(self):
        acquired = DOWNLOAD_IN_PROGRESS.acquire(block=False)
        if not acquired:
            return

        try:
            self._do_downloads()
        finally:
            DOWNLOAD_IN_PROGRESS.release()

    async def do_downloads(self):
        return self.do_downloads_sync()

    def start_downloads(self):
        """
        Start an async task to do downloads.  This does nothing when testing!
        """
        if not PYTEST:
            asyncio.create_task(self.do_downloads())

    @staticmethod
    def reset_downloads():
        """
        Set any incomplete Downloads to `new` so they will be retried.
        """
        with get_db_curs(commit=True) as curs:
            curs.execute("UPDATE download SET status='new' WHERE status='pending' OR status='deferred'")

    def recurring_download(self, url: str, frequency: int, skip_download: bool = False) -> Download:
        """Schedule a recurring download."""
        with get_db_session(commit=True) as session:
            download = self.create_download(url, session=session, skip_download=True)
            download.frequency = frequency

        if skip_download is False and PYTEST:
            self.do_downloads_sync()
        elif skip_download is False:
            self.start_downloads()

        return download

    DOWNLOAD_SORT = ('pending', 'failed', 'new', 'deferred', 'complete')

    @classmethod
    @iterify(list)
    def _downloads_sorter(cls, downloads: List[Download]):
        """
        Downloads should be displayed to the user by status.
        """
        grouped_by_statuses = defaultdict(lambda: [])
        for download in downloads:
            grouped_by_statuses[download.status].append(download)

        # Yield the downloads in the order defined above.
        for sort in cls.DOWNLOAD_SORT:
            yield from grouped_by_statuses[sort]  # converted to a list by iterify()

    @optional_session
    def get_recurring_downloads(self, session: Session = None, limit: int = None):
        """Get all Downloads that will be downloaded in the future."""
        query = session.query(Download).filter(
            Download.frequency != None  # noqa
        ).order_by(
            Download.next_download,  # Sort recurring by which will occur first, then by frequency.
            Download.frequency,  # Sort by frequency if the next_download is the same.
        )
        if limit:
            query = query.limit(limit)
        downloads = query.all()
        downloads = self._downloads_sorter(downloads)
        return downloads

    @optional_session
    def get_once_downloads(self, session: Session = None, limit: int = None):
        """Get all Downloads that will not reoccur."""
        query = session.query(Download).filter(
            Download.frequency == None  # noqa
        ).order_by(
            Download.last_successful_download.desc(),
            Download.id,
        )
        if limit:
            query = query.limit(limit)
        downloads = query.all()
        downloads = self._downloads_sorter(downloads)
        return downloads

    @optional_session
    def renew_recurring_downloads(self, session: Session = None):
        """
        Mark any recurring downloads that are due for download as "new".  Start a download.
        """
        now_ = now()

        recurring = self.get_recurring_downloads(session)
        renewed = False
        for download in recurring:
            if download.next_download < now_:
                download.renew()
                renewed = True

        if renewed:
            session.commit()
            self.start_downloads()

    def get_downloads(self, session: Session) -> List[Download]:
        downloads = session.query(Download).all()
        downloads = list(downloads)
        for download in downloads:
            download.manager = self
        return downloads

    def get_download(self, session: Session, url: str = None, id_: int = None) -> Optional[Download]:
        """
        Attempt to find a Download by its URL or by its id.
        """
        query = session.query(Download)
        if url:
            download = query.filter_by(url=url).one_or_none()
        elif id:
            download = query.filter_by(id=id_).one_or_none()
        else:
            raise ValueError('Cannot find download without some params.')
        if download:
            download.manager = self
        return download

    @optional_session
    def delete_download(self, download_id: int, session: Session = None):
        """
        Delete a Download.  Returns True if a Download was deleted, otherwise return False.
        """
        download = self.get_download(session, id_=download_id)
        if download:
            session.delete(download)
            session.commit()
            return True
        return False

    def kill_download(self, download_id: int):
        """
        Fail a Download, if it is pending, kill the Downloader so the download stops.
        """
        with get_db_session(commit=True) as session:
            download = self.get_download(session, id_=download_id)
            downloader = download.get_downloader()
            logger.warning(f'Killing download {download_id} in {downloader}')
            if download.status == 'pending':
                downloader.kill()
            download.fail()

    def kill(self):
        """
        Kill all downloads.
        """
        self.disabled.set()
        try:
            with get_db_session(commit=True) as session:
                downloads = self.get_pending_downloads(session)
                for download in downloads:
                    downloader = download.get_downloader()
                    downloader.kill()
                    download.defer()
        except Exception as e:
            logger.critical(f'Failed to kill downloads!', exc_info=e)

    def enable(self):
        """
        Enable downloading.  Start downloading.
        """
        self.disabled.clear()
        self.start_downloads()

    FINISHED_STATUSES = ('complete', 'failed')

    def delete_old_once_downloads(self):
        """
        Delete all once-downloads that have expired.  Do not delete downloads that are new, or should be tried again.
        """
        with get_db_session(commit=True) as session:
            downloads = self.get_once_downloads(session)
            one_month = now() - timedelta(days=30)
            for download in downloads:
                if download.status in self.FINISHED_STATUSES and download.last_successful_download and \
                        download.last_successful_download < one_month:
                    session.delete(download)

    def list_downloaders(self) -> List[Downloader]:
        """
        Return a list of the Downloaders available on this Download Manager.
        """
        return list(filter(lambda i: i.listable, self.instances))

    # Downloads should be sorted by their status in a particular order.
    _status_order = '''CASE
                        WHEN (status = 'pending') THEN 0
                        WHEN (status = 'failed') THEN 1
                        WHEN (status = 'new') THEN 2
                        WHEN (status = 'deferred') THEN 3
                        WHEN (status = 'complete') THEN 4
                    END'''

    def get_fe_downloads(self):
        """Get downloads for the Frontend."""
        # Use custom SQL because SQLAlchemy is slow.
        with get_db_curs() as curs:
            stmt = f'''
                SELECT
                    downloader,
                    frequency,
                    id,
                    last_successful_download,
                    next_download,
                    status,
                    url
                FROM download
                WHERE frequency IS NOT NULL
                ORDER BY
                    {self._status_order},
                    next_download,
                    frequency
            '''
            curs.execute(stmt)
            recurring_downloads = list(map(dict, curs.fetchall()))
            recurring_downloads = recursive_replace_tz(recurring_downloads)

            stmt = f'''
                SELECT
                    downloader,
                    frequency,
                    id,
                    last_successful_download,
                    next_download,
                    status,
                    url
                FROM download
                WHERE frequency IS NULL
                ORDER BY
                    {self._status_order},
                    last_successful_download DESC,
                    id
                LIMIT 100
            '''
            curs.execute(stmt)
            once_downloads = list(map(dict, curs.fetchall()))
            once_downloads = recursive_replace_tz(once_downloads)

        data = dict(
            recurring_downloads=recurring_downloads,
            once_downloads=once_downloads,
        )
        return data

    @optional_session
    def get_pending_downloads(self, session: Session) -> List[Download]:
        return session.query(Download).filter_by(status='pending').all()

    @optional_session
    def get_next_download(self, download: Download, session: Session) -> Optional[datetime]:
        """
        If the download is "deferred", download soon.  But, slowly increase the time between attempts.

        If the download is "complete" and the download has a frequency, schedule the download in it's next iteration.
        (Next week, month, etc.)
        """
        if download.status == 'deferred':
            # Increase next_download slowly at first, then by large gaps later.  The largest gap is the download
            # frequency.
            hours = 3 ** (download.attempts or 1)
            seconds = hours * Seconds.hour
            if download.frequency:
                seconds = min(seconds, download.frequency)
            delta = timedelta(seconds=seconds)
            return now() + delta

        if not download.frequency:
            return None
        if not download.id:
            raise ValueError('Cannot get next download when Download is not in DB.')

        freq = download.frequency

        # Keep this Download in it's position within the like-frequency downloads.
        downloads = [i.id for i in session.query(Download).filter_by(frequency=freq).order_by(Download.id)]
        index = downloads.index(download.id)

        # Download was successful.  Spread the same-frequency downloads out over their iteration.
        start_date = local_timezone(datetime(2000, 1, 1))
        # Weeks/months/etc since start_date.
        iterations = ((now() - start_date) // freq).total_seconds()
        # Download slots start the next nearest iteration since 2000-01-01.
        # For example, if a weekly download was performed on 2000-01-01 it will get the same slot within
        # 2000-01-01 to 2000-01-08.
        start_date = start_date + timedelta(seconds=(iterations * freq) + freq)
        end_date = start_date + timedelta(seconds=freq)
        # Get this downloads position in the next iteration.  If a download is performed at the 3rd slot this week,
        # it will be downloaded the 3rd slot of next week.
        zagger = zig_zag(start_date, end_date)
        next_download = [i for i, j in zip(zagger, range(len(downloads)))][index]
        next_download = local_timezone(next_download)
        return next_download

    @optional_session
    def delete_completed(self, session: Session):
        """Delete any completed download records."""
        session.query(Download).filter(Download.status == 'complete').delete()
        session.commit()


# The global DownloadManager.  This should be used everywhere!
download_manager = DownloadManager()
