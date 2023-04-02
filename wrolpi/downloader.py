import asyncio
import logging
import multiprocessing
import os
import pathlib
import traceback
from abc import ABC
from dataclasses import dataclass, field
from datetime import timedelta, datetime
from enum import Enum
from functools import partial
from itertools import filterfalse
from operator import attrgetter
from queue import Empty
from typing import List, Dict, Generator, Iterable
from typing import Tuple, Optional
from urllib.parse import urlparse

import feedparser
import pytz
from feedparser import FeedParserDict
from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from wrolpi import flags
from wrolpi.common import Base, ModelHelper, logger, wrol_mode_check, zig_zag, ConfigFile, WROLPI_CONFIG, \
    background_task, limit_concurrent
from wrolpi.dates import TZDateTime, now, Seconds
from wrolpi.db import get_db_session, get_db_curs, optional_session
from wrolpi.errors import InvalidDownload, UnrecoverableDownloadError
from wrolpi.vars import PYTEST

logger = logger.getChild(__name__)


class DownloadFrequency(int, Enum):
    hourly = 3600
    hours3 = hourly * 3
    hours12 = hourly * 12
    daily = hourly * 24
    weekly = daily * 7
    biweekly = weekly * 2
    days30 = daily * 30
    days90 = daily * 90


@dataclass
class DownloadResult:
    downloads: List[str] = field(default_factory=list)
    error: str = None
    info_json: dict = field(default_factory=dict)
    location: str = None
    success: bool = False
    settings: dict = field(default_factory=dict)


class Download(ModelHelper, Base):  # noqa
    """Model that is used to schedule downloads."""
    __tablename__ = 'download'  # noqa
    id = Column(Integer, primary_key=True)
    url = Column(String, nullable=False)

    attempts = Column(Integer, default=0)
    downloader = Column(Text)
    error = Column(Text)
    frequency = Column(Integer)
    info_json = Column(JSONB)
    last_successful_download = Column(TZDateTime)
    location = Column(Text)
    next_download = Column(TZDateTime)
    settings = Column(JSONB)
    status = Column(String, default='new')
    sub_downloader = Column(Text)
    _manager = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __repr__(self):
        if self.next_download or self.frequency:
            return f'<Download id={self.id} status={self.status} url={repr(self.url)} ' \
                   f'next_download={repr(self.next_download)} frequency={self.frequency} attempts={self.attempts} ' \
                   f'error={bool(self.error)}>'
        return f'<Download id={self.id} status={self.status} url={repr(self.url)} attempts={self.attempts} ' \
               f'error={bool(self.error)}>'

    def __json__(self):
        d = dict(
            downloader=self.downloader,
            frequency=self.frequency,
            id=self.id,
            last_successful_download=self.last_successful_download,
            location=self.location,
            next_download=self.next_download,
            status=self.status,
            sub_downloader=self.sub_downloader,
            url=self.url,
        )
        return d

    def renew(self, reset_attempts: bool = False):
        """Mark this Download as "new" so it will be retried."""
        self.status = 'new'
        if reset_attempts:
            self.attempts = 0

    def defer(self):
        """Download should be tried again after a time."""
        self.status = 'deferred'

    def fail(self):
        """Download should not be attempted again.  A recurring Download will raise an error."""
        if self.frequency:
            raise ValueError('Recurring download should not be failed.')
        self.status = 'failed'

    def started(self):
        """Mark this Download as in progress."""
        self.attempts += 1
        self.status = 'pending'

    def complete(self):
        """Mark this Download as successfully downloaded."""
        self.status = 'complete'
        self.error = None  # clear any old errors
        self.last_successful_download = now()

    def get_downloader(self):
        if self.downloader:
            return self.manager.get_downloader_by_name(self.downloader)

        raise UnrecoverableDownloadError(f'Cannot find downloader for {repr(str(self.url))}')

    @property
    def domain(self):
        return urlparse(self.url).netloc

    @property
    def manager(self) -> 'DownloadManager':
        if self._manager:
            return self._manager
        raise ValueError('No manager has been set!')

    @manager.setter
    def manager(self, value):
        self._manager = value

    def filter_excluded(self, urls: List[str]) -> List[str]:
        """Return any URLs that do not match my excluded_urls."""
        if self.settings and (excluded_urls := self.settings.get('excluded_urls')):
            def excluded(url: str):
                return any(i in url for i in excluded_urls)

            return list(filterfalse(excluded, urls))
        return urls


class Downloader:
    name: str = None
    pretty_name: str = None
    listable: bool = True
    timeout: int = None

    def __init__(self, name: str = None, timeout: int = None):
        if not name and not self.name:
            raise NotImplementedError('Downloader must have a name!')

        self.name: str = self.name or name
        self.timeout: int = timeout or self.timeout
        self._kill = multiprocessing.Event()

        self._manager: DownloadManager = None  # noqa

        download_manager.register_downloader(self)

    def __json__(self):
        return dict(name=self.name, pretty_name=self.pretty_name)

    def __repr__(self):
        return f'<Downloader name={self.name}>'

    async def do_download(self, download: Download) -> DownloadResult:
        raise NotImplementedError()

    @optional_session
    def already_downloaded(self, *urls: List[str], session: Session = None):
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
        """Kill the running download for this Downloader."""
        if not self._kill.is_set():
            self._kill.set()

    def clear(self):
        """Clear any "kill" request for this Downloader."""
        if self._kill.is_set():
            self._kill.clear()

    async def process_runner(self, url: str, cmd: Tuple[str, ...], cwd: pathlib.Path, timeout: int = None,
                             **kwargs) -> Tuple[int, dict]:
        """
        Run a subprocess using the provided arguments.  This process can be killed by the Download Manager.

        Global timeout takes precedence over the timeout argument, unless it is 0.  (Smaller global timeout wins)
        """
        logger.debug(f'{self} launching download process with args: {" ".join(cmd)}')
        start = now()
        proc = await asyncio.create_subprocess_exec(*cmd,
                                                    stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.PIPE,
                                                    cwd=cwd,
                                                    **kwargs)
        pid = proc.pid

        # Timeout can be any positive integer.  Global download timeout takes precedence, unless it is 0.
        # A timeout of 0 means the download will never be killed.
        timeout = WROLPI_CONFIG.download_timeout or timeout or self.timeout
        logger.debug(f'{self} launched download process {pid=} {timeout=} for {url}')

        stdout, stderr = None, None
        try:
            while True:
                task = asyncio.Task(proc.communicate())
                done, pending = await asyncio.wait([task, ], timeout=1)
                # Cancel communicate.
                if pending:
                    pending.pop().cancel()
                if done:
                    # Process finished, get the result of proc.communicate().
                    stdout, stderr = done.pop().result()
                    break
                if proc.returncode:
                    # Process died.
                    stdout, stderr = await proc.communicate()
                    break

                elapsed = (now() - start).total_seconds()
                if timeout and elapsed > timeout:
                    logger.warning(f'Download has exceeded its timeout {elapsed=}')
                    self.kill()

                if self._kill.is_set():
                    logger.warning(f'Killing download {pid=}, {elapsed} seconds elapsed (timeout was not exceeded).')
                    proc.kill()
                    break
        except Exception as e:
            logger.error(f'{self}.process_runner had a download error', exc_info=e)
            raise
        finally:
            self.clear()

            # Output all logs from the process.
            # TODO is there a way to stream this output while the process is running?
            logger.debug(f'Download exited with {proc.returncode}')
            logs = {'stdout': stdout, 'stderr': stderr}

        return proc.returncode, logs


class DownloadManager:
    """
    Runs a collection of workers which will download any URLs in the `download` table.

    Only one download from each domain will be downloaded at a time.  If we only have one domain (example.com) in the
    URLs to be downloaded, then only one worker will be busy.
    """
    manager = multiprocessing.Event()

    def __init__(self):
        self.instances: Tuple[Downloader] = tuple()
        self._instances = dict()
        self.disabled = multiprocessing.Event()
        self.stopped = multiprocessing.Event()

        self.download_queue: multiprocessing.Queue = multiprocessing.Queue()
        self.workers: List[Dict] = []
        self.worker_count: int = 1
        self.worker_alive_frequency = timedelta(minutes=10)

        self.data = multiprocessing.Manager().dict()
        # We haven't started downloads yet, so no domains are downloading.
        self.data['processing_domains'] = []
        self.data['workers'] = dict()

    def __repr__(self):
        return f'<DownloadManager pid={os.getpid()}>'

    def register_downloader(self, instance: Downloader):
        if not isinstance(instance, Downloader):
            raise ValueError(f'Invalid downloader cannot be registered! {instance=}')
        if instance in self.instances:
            raise ValueError(f'Downloader already registered! {instance=}')

        instance.manager = self

        self.instances = (*self.instances, instance)
        self._instances[instance.name] = instance

    async def download_worker(self, num: int):
        """Fetch a download from the queue, perform the download then store the results.

        Calls DownloadManger.start_downloads() after a download completes.
        """
        from wrolpi.db import get_db_session

        pid = os.getpid()
        name = f'{pid}.{num}'
        worker_logger = logger.getChild(f'download_worker.{name}')

        disabled = 'disabled' if self.disabled.is_set() else 'enabled'
        worker_logger.info(f'Starting up.  DownloadManager is {disabled}.')
        last_heartbeat = now()

        while True:
            if self.stopped.is_set():
                # Service may be restarting, close the worker.
                worker_logger.warning("DownloadManager is stopped.  I'm stopping.")
                return

            if now() - last_heartbeat > self.worker_alive_frequency:
                last_heartbeat = now()

            disabled = self.disabled.is_set()

            if disabled:
                # Downloading is disabled, wait for it to enable.
                await asyncio.sleep(1)
                continue

            try:
                download_id, url = self.download_queue.get_nowait()
                worker_logger.debug(f'Got download {download_id}')

                with get_db_session(commit=True) as session:
                    # Mark the download as started in new session so the change is committed.
                    download = session.query(Download).filter_by(id=download_id).one()
                    download.started()

                # Set the Download's manager.  Testing will not use the global manager.
                download.manager = self

                downloader: Downloader = download.get_downloader()
                logger.warning(f'{downloader=}')
                if not downloader:
                    worker_logger.warning(f'Could not find downloader for {download.downloader=}')

                self.data['processing_domains'].append(download.domain)

                try_again = True
                try:
                    if asyncio.iscoroutinefunction(downloader.do_download):
                        result = await downloader.do_download(download)
                    else:
                        result = downloader.do_download(download)
                except UnrecoverableDownloadError as e:
                    # Download failed and should not be retried.
                    worker_logger.warning(f'UnrecoverableDownloadError for {url}', exc_info=e)
                    result = DownloadResult(success=False, error=str(traceback.format_exc()))
                    try_again = False
                except Exception as e:

                    worker_logger.warning(f'Failed to download {url}.  Will be tried again later.', exc_info=e)
                    result = DownloadResult(success=False, error=str(traceback.format_exc()))

                error_len = len(result.error) if result.error else 0
                worker_logger.debug(f'Got success={result.success} from {downloader} with {error_len=}')

                with get_db_session(commit=True) as session:
                    # Modify the download in a new session because downloads may take a long time.
                    download: Download = session.query(Download).filter_by(id=download_id).one()
                    # Use a new location if provided, keep the old location if no new location is provided, otherwise
                    # clear out an outdated location.
                    download.location = result.location or download.location or None
                    # Clear any old errors if the download succeeded.
                    download.error = result.error if result.error else None
                    download.next_download = self.calculate_next_download(download, session)

                    if result.downloads:
                        worker_logger.info(f'Adding {len(result.downloads)} downloads from result of {download.url}')
                        urls = download.filter_excluded(result.downloads)
                        self.create_downloads(urls, session, downloader_name=download.sub_downloader,
                                              settings=result.settings)

                    if try_again is False and not download.frequency:
                        # Only once-downloads can fail.
                        download.fail()
                    elif result.success:
                        download.complete()
                    else:
                        download.defer()

                # Remove this domain from the running list.
                self._remove_domain(download.domain)
                # Request any new downloads be added to the queue.
                background_task(self.queue_downloads())
                # Save the config now that the Download has finished.
                background_task(save_downloads_config())
            except asyncio.CancelledError:
                worker_logger.warning('Canceled!')
                self.download_queue.task_done()
                return
            except Empty:
                # No work yet.
                await asyncio.sleep(0.1)
            except Exception as e:
                worker_logger.warning(f'Unexpected error', exc_info=e)

    def log(self, message: str, level=logging.DEBUG, exc_info=None):
        logger.log(level, f'{self} {message}', exc_info=exc_info)

    def log_info(self, message: str):
        return self.log(message, logging.INFO)

    def log_debug(self, message: str):
        return self.log(message, logging.DEBUG)

    def log_error(self, message: str, exc_info=None):
        return self.log(message, logging.ERROR, exc_info)

    def log_warning(self, message: str):
        return self.log(message, logging.WARNING)

    def _add_domain(self, domain: str):
        """Add a domain to the processing list.

        Raises ValueError if the domain is already processing."""
        processing_domains = self.data['processing_domains']
        if domain in processing_domains:
            raise ValueError(f'Domain already being downloaded! {domain}')
        self.data['processing_domains'] = [*processing_domains, domain]

    def _remove_domain(self, domain: str):
        """Remove a domain from the processing list."""
        self.data['processing_domains'] = [i for i in self.data['processing_domains'] if i != domain]

    @wrol_mode_check
    def start_workers(self, loop=None):
        """Start all download worker tasks.  Does nothing if they are already running."""
        if not self.workers:
            if not loop:
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    # Loop isn't running, start one.  Probably testing.
                    loop = asyncio.get_event_loop()

            for i in range(self.worker_count):
                coro = self.download_worker(i)
                task = loop.create_task(coro)
                self.workers.append(task)

    def workers_running(self):
        for task in self.workers:
            if not task.done():
                return True
        return False

    def cancel_workers(self):
        if self.workers_running():
            for task in self.workers:
                task.cancel()

    async def perpetual_download(self):
        """
        A method that calls itself forever.  It will queue new downloads when they are ready.

        Only one of these can be running at a time.
        """
        if self.manager.is_set():
            # Only one manager needs to be running.
            return

        self.manager.set()

        async def _perpetual_download():
            self.log_debug('perpetual download is alive')
            if self.stopped.is_set():
                return

            await download_manager.do_downloads()
            await asyncio.sleep(30)
            background_task(_perpetual_download())

        background_task(_perpetual_download())

    def get_downloader_by_name(self, name: str) -> Optional[Downloader]:
        """Attempt to find a registered Downloader by its name.  Returns None if it cannot be found."""
        if downloader := self._instances.get(name):
            return downloader
        raise InvalidDownload(f'Cannot find downloader with name {name}')

    def get_or_create_download(self, url: str, session: Session) -> Download:
        """Get a Download by its URL, if it cannot be found create one."""
        if not url:
            raise ValueError('Download must have a URL')

        download = self.get_download(session, url=url)
        if not download:
            if url in DOWNLOAD_MANAGER_CONFIG.skip_urls:
                raise InvalidDownload(
                    f'Refusing to download {url} because it is in the download_manager.yaml skip list')
            download = Download(url=url, status='new')
            session.add(download)
            session.flush()
        download.manager = self
        return download

    @optional_session
    def create_downloads(self, urls: List[str], downloader_name: str, session: Session = None,
                         reset_attempts: bool = False, sub_downloader_name: str = None, settings: dict = None) \
            -> List[Download]:
        """Schedule all URLs for download.  If one cannot be downloaded, none will be added."""
        if not all(urls):
            raise ValueError('Download must have a URL')

        downloads = []
        # Throws an error if no downloader is found.
        self.get_downloader_by_name(downloader_name)

        with session.transaction:
            for url in urls:
                if url in DOWNLOAD_MANAGER_CONFIG.skip_urls and reset_attempts:
                    # User manually entered this download, remove it from the skip list.
                    self.remove_from_skip_list(url)
                elif url in DOWNLOAD_MANAGER_CONFIG.skip_urls:
                    self.log_warning(f'Skipping {url} because it is in the download_manager.yaml skip list.')
                    continue

                download = self.get_or_create_download(url, session)
                # Download may have failed, try again.
                download.renew(reset_attempts=reset_attempts)
                download.downloader = downloader_name
                download.sub_downloader = sub_downloader_name
                download.settings = settings
                downloads.append(download)

        try:
            # Start downloading ASAP.
            background_task(self.queue_downloads())
            # Save the config now that new Downloads exist.
            background_task(save_downloads_config())
        except RuntimeError:
            # Event loop isn't running.  Probably testing?
            if not PYTEST:
                self.log_info(f'Unable to queue downloads after creating {len(downloads)} download(s).')

        return downloads

    @optional_session
    def create_download(self, url: str, downloader_name: str, session: Session = None, reset_attempts: bool = False,
                        sub_downloader_name: str = None, settings: Dict = None) -> Download:
        """Schedule a URL for download.  If the URL failed previously, it may be retried."""
        downloads = self.create_downloads([url], session=session, downloader_name=downloader_name,
                                          reset_attempts=reset_attempts, sub_downloader_name=sub_downloader_name,
                                          settings=settings)
        return downloads[0]

    @optional_session
    def recurring_download(self, url: str, frequency: int, downloader_name: str, session: Session = None,
                           sub_downloader_name: str = None, reset_attempts: bool = False,
                           settings: Dict = None) -> Download:
        """Schedule a recurring download."""
        if not frequency or not isinstance(frequency, int):
            raise ValueError('Recurring download must have a frequency!')

        download, = self.create_downloads([url, ], session=session, downloader_name=downloader_name,
                                          reset_attempts=reset_attempts, sub_downloader_name=sub_downloader_name,
                                          settings=settings)
        download.frequency = frequency
        session.commit()

        return download

    @wrol_mode_check
    @optional_session
    async def queue_downloads(self, session: Session = None):
        """Put all downloads in queue.  Will only queue downloads if there are workers to take them.  Each worker
        only receives one domain, this is to prevent downloading from one domain many times at once."""
        if self.disabled.is_set() or self.stopped.is_set():
            # Don't queue downloads when disabled.
            return

        if len(self.data['processing_domains']) >= len(self.workers):
            return

        # Find download whose domain isn't already being downloaded.
        new_downloads = list(session.query(Download).filter(
            Download.status == 'new',
            Download.domain not in self.data['processing_domains'],
        ).order_by(
            Download.frequency.is_(None),
            Download.frequency,
            Download.id))  # noqa
        count = 0
        for download in new_downloads:
            download.manager = self  # Assign this Download to this manager.
            domain = download.domain
            if domain not in self.data['processing_domains']:
                self._add_domain(domain)
                self.download_queue.put((download.id, download.url))
                count += 1
        if count:
            self.log_debug(f'Added {count} downloads to queue.')

    async def do_downloads(self):
        """Schedule any downloads that are new.

        Warning: Downloads will still be running even after this returns!  See `wait_for_all_downloads`.
        """
        if self.disabled.is_set():
            return

        try:
            self.renew_recurring_downloads()
        except Exception as e:
            self.log_error(f'Unable to renew downloads!', exc_info=e)

        try:
            self.delete_old_once_downloads()
        except Exception as e:
            self.log_error(f'Unable to delete old downloads!', exc_info=e)

        await self.queue_downloads()

    async def wait_for_all_downloads(self):
        """Wait for all Downloads in queue AND any new Downloads to complete.

        THIS METHOD IS FOR TESTING.
        """
        while True:
            await asyncio.sleep(0.1)

            if not self.workers_running():
                raise ValueError('No workers are running!')

            await self.queue_downloads()

            try:
                next(self.get_new_downloads())
                continue
            except StopIteration:
                pass

            if self.download_queue.empty():
                # Queue is empty.
                break

    @staticmethod
    def reset_downloads():
        """Set any incomplete Downloads to `new` so they will be retried."""
        with get_db_curs(commit=True) as curs:
            curs.execute("UPDATE download SET status='new' WHERE status='pending' OR status='deferred'")

    DOWNLOAD_SORT = ('pending', 'failed', 'new', 'deferred', 'complete')

    @optional_session
    def get_new_downloads(self, session: Session) -> Generator[Download, None, None]:
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
        return downloads

    @optional_session
    def renew_recurring_downloads(self, session: Session = None):
        """Mark any recurring downloads that are due for download as "new".  Start a download."""
        now_ = now()

        recurring = self.get_recurring_downloads(session)
        renewed_count = 0
        for download in recurring:
            # A new download may not have a `next_download`, create it if necessary.
            download.next_download = download.next_download or self.calculate_next_download(download, session=session)
            if download.next_download < now_:
                download.renew()
                renewed_count += 1

        if renewed_count:
            self.log_debug(f'Renewed {renewed_count} recurring downloads')
            session.commit()

            # Save the config now that some Downloads renewed.
            background_task(save_downloads_config())

    def get_downloads(self, session: Session) -> List[Download]:
        downloads = list(session.query(Download).all())
        for download in downloads:
            download.manager = self
        return downloads

    def get_download(self, session: Session, url: str = None, id_: int = None) -> Optional[Download]:
        """Attempt to find a Download by its URL or by its id."""
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
        """Delete a Download.  Returns True if a Download was deleted, otherwise return False."""
        download = self.get_download(session, id_=download_id)
        if download:
            session.delete(download)
            session.commit()
            # Save the config because a download was deleted.
            if PYTEST:
                save_downloads_config()
            else:
                background_task(save_downloads_config())
            return True
        return False

    def kill_download(self, download_id: int):
        """Fail a Download. If it is pending, kill the Downloader so the download stops."""
        with get_db_session(commit=True) as session:
            download = self.get_download(session, id_=download_id)
            downloader = download.get_downloader()
            self.log_warning(f'Killing download {download_id} in {downloader}')
            if download.status == 'pending':
                downloader.kill()
            download.fail()

    def disable(self):
        """Stop all downloads and downloaders.  Workers will stay idle."""
        self.log_info('Disabling downloads and downloaders.')
        self.disabled.set()
        for downloader in self.instances:
            downloader.kill()
        if flags.db_up.is_set():
            # Only defer downloads if the DB is up.
            for download in self.get_pending_downloads():
                download.defer()
        self.cancel_workers()

    def stop(self):
        """Stop all downloads, downloaders and workers, defer all pending downloads."""
        self.log_warning('Stopping all workers')
        self.stopped.set()
        self.disable()

    def enable(self, loop=None):
        """Enable downloading.  Start downloading.  Start workers."""
        self.log_info('Enabling downloading')
        for downloader in self.instances:
            downloader.clear()
        self.stopped.clear()
        self.disabled.clear()
        self.start_workers(loop)

        try:
            background_task(self.perpetual_download())
            background_task(self.do_downloads())
        except RuntimeError:
            # This may not work while testing.
            if not PYTEST:
                raise

    FINISHED_STATUSES = ('complete', 'failed')

    def delete_old_once_downloads(self):
        """Delete all once-downloads that have expired.

        Do not delete downloads that are new, or should be tried again."""
        with get_db_session(commit=True) as session:
            downloads = self.get_once_downloads(session)
            one_month = now() - timedelta(days=30)
            for download in downloads:
                if download.status in self.FINISHED_STATUSES and download.last_successful_download and \
                        download.last_successful_download < one_month:
                    session.delete(download)

    def list_downloaders(self) -> List[Downloader]:
        """Return a list of the Downloaders available on this Download Manager."""
        return [i for i in self.instances if i.listable]

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
                    url,
                    location,
                    error
                FROM download
                WHERE frequency IS NOT NULL
                ORDER BY
                    {self._status_order},
                    next_download,
                    frequency
            '''
            curs.execute(stmt)
            recurring_downloads = list(map(dict, curs.fetchall()))

            stmt = f'''
                SELECT
                    downloader,
                    error,
                    frequency,
                    id,
                    last_successful_download,
                    location,
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

        data = dict(
            recurring_downloads=recurring_downloads,
            once_downloads=once_downloads,
        )
        return data

    def get_summary(self) -> dict:
        """
        Get a summary of what Downloads are happening as well as the status of the DownloadManager.
        """
        with get_db_curs() as curs:
            stmt = """
                SELECT
                 COUNT(*) FILTER (WHERE status = 'pending') AS pending_downloads,
                 COUNT(*) FILTER (WHERE frequency IS NOT NULL) AS recurring_downloads
                FROM download
                """
            curs.execute(stmt)
            counts = list(map(dict, curs.fetchall()))[0]
        summary = dict(
            pending=counts['pending_downloads'],
            recurring=counts['recurring_downloads'],
            disabled=self.disabled.is_set(),
            stopped=self.stopped.is_set(),
        )
        return summary

    @optional_session
    def get_pending_downloads(self, session: Session) -> List[Download]:
        downloads = session.query(Download).filter_by(status='pending').all()
        for download in downloads:
            download.manager = self
        return downloads

    @staticmethod
    @optional_session
    def calculate_next_download(download: Download, session: Session) -> Optional[datetime]:
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
        start_date = datetime(2000, 1, 1).replace(tzinfo=pytz.UTC)
        # Weeks/months/etc. since start_date.
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
        next_download = next_download
        return next_download

    @optional_session
    def delete_completed(self, session: Session):
        """Delete any completed download records."""
        session.query(Download).filter(
            Download.status == 'complete',
            Download.frequency == None,  # noqa
        ).delete()
        session.commit()

    @optional_session
    def delete_failed(self, session: Session):
        """Delete any failed download records."""
        failed_downloads = session.query(Download).filter(
            Download.status == 'failed',
            Download.frequency == None,  # noqa
        ).all()

        # Add all downloads to permanent skip list.
        ids = [i.id for i in failed_downloads]
        self.add_to_skip_list(*(i.url for i in failed_downloads))

        # Delete all failed once-downloads.
        session.execute('DELETE FROM download WHERE id = ANY(:ids)', {'ids': ids})
        session.commit()

    @staticmethod
    def add_to_skip_list(*urls: str):
        DOWNLOAD_MANAGER_CONFIG.skip_urls = list(set(DOWNLOAD_MANAGER_CONFIG.skip_urls) | set(urls))
        DOWNLOAD_MANAGER_CONFIG.save()

    @staticmethod
    def remove_from_skip_list(url: str):
        DOWNLOAD_MANAGER_CONFIG.skip_urls = [i for i in DOWNLOAD_MANAGER_CONFIG.skip_urls if i != url]
        DOWNLOAD_MANAGER_CONFIG.save()


# The global DownloadManager.  This should be used everywhere!
download_manager = DownloadManager()


class DownloadMangerConfig(ConfigFile):
    file_name = 'download_manager.yaml'
    default_config = dict(
        skip_urls=[],
        downloads=[],
    )

    @property
    def skip_urls(self) -> List[str]:
        return self._config['skip_urls']

    @skip_urls.setter
    def skip_urls(self, value: List[str]):
        self.update({'skip_urls': value})

    @property
    def downloads(self) -> List[dict]:
        return self._config['downloads']

    @downloads.setter
    def downloads(self, value: List[dict]):
        self.update({'downloads': value})


DOWNLOAD_MANAGER_CONFIG: DownloadMangerConfig = DownloadMangerConfig()


def set_test_download_manager_config(enabled: bool):
    global DOWNLOAD_MANAGER_CONFIG
    DOWNLOAD_MANAGER_CONFIG = None
    if enabled:
        DOWNLOAD_MANAGER_CONFIG = DownloadMangerConfig()


@optional_session(commit=False)
async def save_downloads_config(session: Session):
    """Fetch all Downloads from the DB, save them to the Download Manager Config."""
    downloads: Iterable[Download] = session.query(Download).order_by(Download.url)
    config = []
    for download in downloads:
        if download.last_successful_download and not download.frequency:
            # This once-download has completed, do not save it.
            continue
        config.append(dict(
            downloader=download.downloader,
            frequency=download.frequency,
            last_successful_download=download.last_successful_download,
            next_download=download.next_download,
            status=download.status,
            sub_downloader=download.sub_downloader,
            url=download.url,
        ))
    if config != DOWNLOAD_MANAGER_CONFIG.downloads:
        # Only save if there are changes.
        DOWNLOAD_MANAGER_CONFIG.downloads = config


@optional_session
@limit_concurrent(1)
async def import_downloads_config(session: Session):
    """Upsert all Downloads in the Download Manager Config into the DB.

    The config is the source of truth."""
    if not PYTEST and not flags.db_up.is_set():
        logger.warning(f'Refusing to import downloads config when DB is not up.')
        return

    try:
        logger.warning('Importing downloads in config')

        downloads_by_url = {i['url']: i for i in DOWNLOAD_MANAGER_CONFIG.downloads}
        existing_downloads = list(session.query(Download))
        for existing in existing_downloads:
            download = downloads_by_url.pop(existing.url, None)
            if download:
                # Download in config already exists, update the DB record.
                # The config is the source of truth.
                existing.downloader = download['downloader']
                existing.frequency = download['frequency']
                existing.last_successful_download = download['last_successful_download']
                existing.next_download = download['next_download']
                existing.status = download['status']
                existing.sub_downloader = download['sub_downloader']
                logger.debug(f'Updating download {existing.url} with {download}')

        for download in downloads_by_url.values():
            # These downloads are new, import them.
            download = Download(
                downloader=download['downloader'],
                frequency=download['frequency'],
                last_successful_download=download['last_successful_download'],
                next_download=download['next_download'],
                status=download['status'],
                sub_downloader=download['sub_downloader'],
                url=(url := download['url']),
            )
            session.add(download)
            logger.info(f'Adding new download {url}')

        session.commit()
    except Exception as e:
        logger.error('Failed to import downloads', exc_info=e)
        raise


def parse_feed(url: str) -> FeedParserDict:
    """Calls `feedparser.parse`, used for testing."""
    return feedparser.parse(url)


class RSSDownloader(Downloader, ABC):
    """Downloads an RSS feed and creates new downloads for every unique link in the feed."""
    name = 'rss'
    pretty_name = 'RSS'
    listable = False

    def __repr__(self):
        return '<RSSDownloader>'

    @classmethod
    def valid_url(cls, url: str) -> Tuple[bool, Optional[dict]]:
        """Attempts to parse an RSS Feed.  If it succeeds, it returns a FeedParserDict as a dictionary."""
        feed = parse_feed(url)
        feed = dict(feed)
        if feed['bozo']:
            # Feed did not parse.
            return False, {}
        return True, dict(feed=feed)

    def do_download(self, download: Download) -> DownloadResult:
        if isinstance(download.info_json, dict) and download.info_json.get('feed'):
            feed = download.info_json['feed']
        else:
            # self.valid_url was not called by the manager, do it here.
            feed: FeedParserDict = parse_feed(download.url)
            if feed['bozo'] and not self.acceptable_bozo_errors(feed):
                # Feed did not parse
                return DownloadResult(success=False, error='Failed to parse RSS feed')

        if not isinstance(feed, dict) or not feed.get('entries'):
            # RSS parsed but does not have entries.
            return DownloadResult(success=False, error='RSS feed did not have any entries')

        # Only download URLs that have not yet been downloaded.
        urls = []
        sub_downloader = self.manager.get_downloader_by_name(download.sub_downloader)
        if not sub_downloader:
            raise ValueError(f'Unable to find sub_downloader for {download.url}')

        for idx, entry in enumerate(feed['entries']):
            if url := entry.get('link'):
                urls.append(url.strip())
            else:
                logger.warning(f'RSS entry {idx} did not have a link!')

        # Only download new URLs.
        urls = [i for i in urls if i not in [i.url for i in sub_downloader.already_downloaded(*urls)]]

        return DownloadResult(success=True, downloads=urls)

    @staticmethod
    def acceptable_bozo_errors(feed):
        """Feedparser can report some errors, some we can ignore."""
        if 'document declared as' in str(feed['bozo_exception']):
            # Feed's encoding does not match what is declared, this is fine.
            return True
        return False


rss_downloader = RSSDownloader()
