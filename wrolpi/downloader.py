import asyncio
import contextlib
import inspect
import logging
import multiprocessing
import os
import pathlib
import tempfile
import traceback
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import timedelta, datetime
from enum import Enum
from http import HTTPStatus
from itertools import filterfalse
from typing import List, Dict, Generator, Iterable, Coroutine
from typing import Tuple, Optional
from urllib.parse import urlparse

import feedparser
import pytz
from feedparser import FeedParserDict
from sqlalchemy import Column, Integer, String, Text, ForeignKey, ARRAY
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, relationship
from sqlalchemy.sql import Delete

from wrolpi import flags
from wrolpi.api_utils import api_app, perpetual_signal
from wrolpi.cmd import which, run_command, CommandResult
from wrolpi.common import Base, ModelHelper, logger, wrol_mode_check, zig_zag, ConfigFile, \
    wrol_mode_enabled, background_task, get_absolute_media_path, timer, aiohttp_get, \
    get_download_info, trim_file_name, get_wrolpi_config, TRACE_LEVEL
from wrolpi.dates import TZDateTime, now, Seconds
from wrolpi.db import get_db_session, get_db_curs, optional_session
from wrolpi.errors import InvalidDownload, UnrecoverableDownloadError, UnknownDownload, ValidationError, DownloadError
from wrolpi.events import Events
from wrolpi.media_path import MediaPathType
from wrolpi.switches import register_switch_handler, ActivateSwitchMethod, await_switches
from wrolpi.vars import PYTEST, SIMULTANEOUS_DOWNLOAD_DOMAINS

logger = logger.getChild(__name__)

ARIA2C_PATH = which('aria2c', '/usr/bin/aria2c')


@perpetual_signal(sleep=1 if PYTEST else 5)
async def perpetual_download_worker():
    async with flags.db_up.wait_for():
        pass

    if not get_download_manager_config().successful_import:
        logger.trace(f'Not starting perpetual download worker because config was not imported')
        return

    if download_manager.is_stopped:
        logger.trace(f'Not starting perpetual download worker because download manager is stopped')
        return

    try:
        async with flags.have_internet.wait_for(timeout=5):
            pass
    except TimeoutError:
        # Internet is not up.
        return

    await download_manager.do_downloads()


class DownloadFrequency(int, Enum):
    hourly = 3600
    hours3 = hourly * 3
    hours12 = hourly * 12
    daily = hourly * 24
    weekly = daily * 7
    biweekly = weekly * 2
    days30 = daily * 30
    days90 = daily * 90
    days180 = daily * 180


@dataclass
class DownloadResult:
    downloads: List[str] = field(default_factory=list)
    error: str = None
    info_json: dict = field(default_factory=dict)
    location: str = None
    success: bool = False
    settings: dict = field(default_factory=dict)


class DownloadStatus(str, Enum):
    new = 'new'
    pending = 'pending'
    complete = 'complete'
    failed = 'failed'
    deferred = 'deferred'


class Download(ModelHelper, Base):  # noqa
    """Model that is used to schedule downloads."""
    __tablename__ = 'download'  # noqa
    id = Column(Integer, primary_key=True)
    url = Column(String, nullable=False, unique=True)

    attempts = Column(Integer, default=0)
    destination: pathlib.Path = Column(MediaPathType)  # '/media/wrolpi/videos/WROLPi'
    downloader = Column(Text)  # 'videos', 'archive', 'kiwix_zim', etc.
    sub_downloader = Column(Text)  # The downloader any returned downloads should be sent.
    error = Column(Text)  # traceback from an error during downloading.
    frequency = Column(Integer)  # seconds between re-downloading.
    info_json = Column(JSONB)  # information retrieved WHILE downloading (from yt-dlp)
    last_successful_download = Column(TZDateTime)
    location = Column(Text)  # Relative App URL where the downloaded item can be viewed.
    next_download = Column(TZDateTime)
    settings = Column(JSONB)  # information about how the download should happen (video_resolution, etc.)
    status = Column(String, default=DownloadStatus.new)  # `DownloadStatus` enum.
    tag_names = Column(ARRAY(Text))

    # A Download may be associated with a Channel (downloads all Channel videos, or a playlist, etc.).
    channel_id = Column(Integer, ForeignKey('channel.id'))
    channel = relationship('Channel', primaryjoin='Download.channel_id==Channel.id', back_populates='downloads')

    def __repr__(self):
        if self.next_download or self.frequency:
            return f'<Download id={self.id} status={self.status} url={repr(self.url)} ' \
                   f'next_download={repr(self.next_download)} frequency={self.frequency} attempts={self.attempts} ' \
                   f'error={bool(self.error)}>'
        return f'<Download id={self.id} status={self.status} url={repr(self.url)} attempts={self.attempts} ' \
               f'error={bool(self.error)}>'

    def __json__(self) -> dict:
        d = dict(
            attempts=self.attempts,
            channel_id=self.channel_id,
            downloader=self.downloader,
            frequency=self.frequency,
            destination=self.destination,
            id=self.id,
            last_successful_download=self.last_successful_download,
            location=self.location,
            next_download=self.next_download,
            settings=self.settings,
            status=self.status,
            sub_downloader=self.sub_downloader,
            tag_names=self.tag_names,
            url=self.url,
        )
        return d

    def renew(self, reset_attempts: bool = False):
        """Mark this Download as "new" so it will be retried."""
        self.status = DownloadStatus.new
        if reset_attempts:
            self.attempts = 0

    @property
    def is_new(self) -> bool:
        return self.status == DownloadStatus.new

    def defer(self):
        """Download should be tried again after a time."""
        self.status = DownloadStatus.deferred

    @property
    def is_deferred(self) -> bool:
        return self.status == DownloadStatus.deferred

    def fail(self):
        """Download should not be attempted again.  A recurring Download will raise an error."""
        if self.frequency:
            raise ValueError('Recurring download should not be failed.')
        self.status = DownloadStatus.failed

    @property
    def is_failed(self) -> bool:
        return self.status == DownloadStatus.failed

    def started(self):
        """Mark this Download as in progress."""
        self.attempts += 1
        self.status = DownloadStatus.pending

    @property
    def is_pending(self) -> bool:
        return self.status == DownloadStatus.pending

    def complete(self):
        """Mark this Download as successfully downloaded."""
        self.status = DownloadStatus.complete
        self.error = None  # clear any old errors
        self.last_successful_download = now()

    @property
    def is_complete(self) -> bool:
        return self.status == DownloadStatus.complete

    def get_downloader(self):
        if self.downloader:
            return download_manager.find_downloader_by_name(self.downloader)

        raise UnrecoverableDownloadError(f'Cannot find downloader for {repr(str(self.url))}')

    @property
    def domain(self):
        return urlparse(self.url).netloc

    def filter_excluded(self, urls: List[str]) -> List[str]:
        """Return any URLs that do not match my excluded_urls."""
        if self.settings and (excluded_urls := self.settings.get('excluded_urls')):
            excluded_urls = excluded_urls.split(',')

            def excluded(url: str):
                return any(i in url for i in excluded_urls)

            return list(filterfalse(excluded, urls))
        return urls

    def add_to_skip_list(self):
        download_manager.add_to_skip_list(self.url)

    def delete(self, add_to_skip_list: bool = True):
        # Do not download this automatically again.  This saves the config.
        if add_to_skip_list:
            self.add_to_skip_list()

        session = Session.object_session(self)

        session.delete(self)
        session.commit()
        if self.channel_id:
            # Save Channels config if this download was associated with a Channel.
            from modules.videos.lib import save_channels_config
            save_channels_config.activate_switch()
        # Save download config again because this download is now removed from the download lists.
        save_downloads_config.activate_switch()

    @staticmethod
    def get_by_id(id_: int, session: Session = None) -> Optional['Download']:
        download = session.query(Download).filter(Download.id == id_).one_or_none()
        return download

    @classmethod
    @optional_session
    def find_by_id(cls, id_: int, session: Session = None) -> 'Download':
        if download := cls.get_by_id(id_, session):
            return download
        raise UnknownDownload(f'Cannot find Download with id: {id_}')

    @staticmethod
    @optional_session
    def get_by_url(url: str, session: Session = None) -> Optional['Download']:
        download = session.query(Download).filter(Download.url == url).one_or_none()
        return download

    @classmethod
    @optional_session
    def find_by_url(cls, url: str, session: Session = None) -> 'Download':
        if download := cls.get_by_url(url, session):
            return download
        raise UnknownDownload(f'Cannot find Download with URL: {url}')

    @classmethod
    @optional_session
    def get_all_by_destination(cls, destination: str | pathlib.Path, session: Session = None) -> List['Download']:
        destination = str(destination)
        downloads = session.query(Download).filter_by(destination=destination).all()
        return downloads


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

        self._manager: DownloadManager = None  # noqa

        download_manager.register_downloader(self)

    def __json__(self) -> dict:
        return dict(name=self.name, pretty_name=self.pretty_name)

    def __repr__(self):
        return f'<Downloader name={self.name}>'

    async def do_download(self, download: Download) -> DownloadResult:
        raise NotImplementedError()

    @optional_session
    def already_downloaded(self, *urls: List[str], session: Session = None):
        raise NotImplementedError()

    async def process_runner(self, download: Download, cmd: Tuple[str | pathlib.Path, ...], cwd: pathlib.Path,
                             timeout: int = None, debug: bool = True) -> CommandResult:
        """
        Run a subprocess using the provided arguments.  This process can be killed by the Download Manager.

        Global timeout takes precedence over the timeout argument, unless it is 0.  (Smaller global timeout wins)
        """
        if cwd and not cwd.is_dir():
            raise RuntimeError('cwd directory does not exist')

        timeout = get_wrolpi_config().download_timeout or timeout or self.timeout
        coro = run_command(cmd, cwd=cwd, timeout=timeout, log_command=debug)
        result = await self.cancel_wrapper(coro, download)

        if logger.isEnabledFor(TRACE_LEVEL):
            for line in result.stdout.decode().splitlines():
                logger.trace(line)
            for line in result.stderr.decode().splitlines():
                logger.error(line)

        return result

    @staticmethod
    async def cancel_wrapper(coro: Coroutine, download: Download):
        """
        Converts an async coroutine to a task.  If DownloadManager receives a kill request, this method will cancel
        the task.
        """
        download_id = download.id
        task = asyncio.create_task(coro)
        while not task.done():
            if download_manager.download_is_killed(download_id) or not download_manager.can_download:
                logger.warning(f'Cancel download of {download.url}')
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError as e:
                    logger.info(f'Successful cancel of {download.url}', exc_info=e)
                    return DownloadResult(
                        success=False,
                        error='Download was canceled',
                    )
                finally:
                    download_manager.unkill_download(download_id)
            else:
                # Wait for the download to complete.  Cancel if requested.
                await asyncio.sleep(0.1)

        # Return the result of the download attempt.
        return task.result()

    @staticmethod
    async def get_meta4_contents(url: str) -> bytes | None:
        try:
            meta4_url = f'{url}.meta4'
            async with aiohttp_get(meta4_url, timeout=60) as response:
                if response.status == HTTPStatus.OK:
                    contents = await response.content.read()
                    try:
                        root = ET.fromstring(contents)
                        if root.tag == '{urn:ietf:params:xml:ns:metalink4}metalink':
                            return contents
                        if root.tag == '{urn:ietf:params:xml:ns:metalink}metalink':
                            return contents
                        logger.debug(f'meta4 file was not a metalink file: {meta4_url}')
                    except Exception as e:
                        logger.debug(f'Failed to parse XML {meta4_url}', exc_info=e)
        except Exception as e:
            logger.debug(f'Failed to fetch meta4 file {url}', exc_info=e)

        return None

    async def download_file(self, download: Download, url: str, destination: pathlib.Path, check_for_meta4: bool = True) \
            -> pathlib.Path:
        from wrolpi.files.lib import glob_shared_stem

        if not ARIA2C_PATH:
            raise DownloadError('Cannot find aria2c executable')

        # Log download time.
        with timer('download_file', level='info'):
            meta4_contents = None
            if check_for_meta4:
                meta4_contents = await self.get_meta4_contents(url)

            info = await get_download_info(url)

            # TODO verify that this output_path is exclusive.
            output_path = destination / trim_file_name(info.name)

            with tempfile.NamedTemporaryFile(suffix='.meta4') as meta4_path:
                cmd = (
                    ARIA2C_PATH,
                    '-l', '-',
                    '-c',  # Continue downloading a partially downloaded file.
                    '-j3',  # concurrent downloads
                    '-s3',  # split jobs
                    '-d', destination,
                    url
                )
                meta4_path = pathlib.Path(meta4_path.name)
                if meta4_contents:
                    meta4_path.write_bytes(meta4_contents)
                    cmd = (*cmd,
                           '-M', meta4_path,
                           )

                result = await self.process_runner(download, cmd, destination)
                error = result.stderr.decode()

                if result.return_code != 0:
                    raise DownloadError(f'{error}\n\nFileDownloader failed with return code {result.return_code}')

                if not output_path.is_file():
                    raise DownloadError(f'{error}\n\nOutput file not found: {output_path}')

            # Delete any trailing meta4 files.
            matching_files = glob_shared_stem(output_path)
            for file in matching_files:
                if file.name.endswith('.meta4'):
                    logger.warning(f'Deleting meta4 file: {file}')
                    file.unlink()
                if file.name.endswith('.aria2'):
                    logger.trace(f'Deleting aria2 file: {file}')
                    file.unlink()

            return output_path


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

    def __repr__(self):
        return f'<DownloadManager pid={os.getpid()}>'

    @property
    def disabled(self):
        # Server is going to keep running, but downloads should stop.
        return api_app.shared_ctx.download_manager_disabled

    @property
    def is_disabled(self) -> bool:
        return self.disabled.is_set()

    def disable(self):
        """Stop all downloads and downloaders."""
        if not self.disabled.is_set():
            self.disabled.set()

    @property
    def stopped(self):
        # Server is stopping and perpetual download should stop.
        return api_app.shared_ctx.download_manager_stopped

    @property
    def is_stopped(self) -> bool:
        return self.stopped.is_set()

    def stop(self):
        """Stop all downloads, downloaders and workers.  This is called when the server is shutting down."""
        if not self.is_stopped:
            self.stopped.set()
        self.disable()

    async def enable(self):
        """Enable downloading.

        perpetual_download_worker will start downloading.
        """
        self.log_info('Enabling downloading')
        self.stopped.clear()
        self.disabled.clear()

    @property
    def can_download(self) -> bool:
        """Returns True only if all steps necessary for downloading have been met."""
        if PYTEST:
            return True
        if self.is_disabled:
            # DownloadManager has been disabled and should not download.
            return False
        if self.is_stopped:
            # DownloadManager has been stopped and system is probably restarting.
            return False
        if not flags.have_internet.is_set():
            # Do not download without internet.
            return False
        if wrol_mode_enabled():
            # Do not download with WROL Mode enabled.
            return False
        if get_download_manager_config().successful_import:
            # Finally, allow downloading because config was valid and imported.
            return True
        # Do not download by default.
        return False

    @property
    def processing_domains(self):
        return api_app.shared_ctx.download_manager_data['processing_domains']

    @processing_domains.setter
    def processing_domains(self, value: list):
        api_app.shared_ctx.download_manager_data.update({'processing_domains': value})

    def _add_processing_domain(self, domain: str):
        self.processing_domains = list(self.processing_domains) + [domain, ]

    def _delete_processing_domain(self, domain: str):
        self.processing_domains = [i for i in self.processing_domains if i != domain]

    def register_downloader(self, instance: Downloader):
        if not isinstance(instance, Downloader):
            raise ValueError(f'Invalid downloader cannot be registered! {instance=}')
        if instance in self.instances:
            raise ValueError(f'Downloader already registered! {instance=}')

        self.instances = (*self.instances, instance)
        self._instances[instance.name] = instance

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

    def find_downloader_by_name(self, name: str) -> Optional[Downloader]:
        """Attempt to find a registered Downloader by its name.  Raises error if it cannot be found."""
        if downloader := self._instances.get(name):
            return downloader
        raise InvalidDownload(f'Cannot find downloader with name {name}')

    def get_or_create_download(self, url: str, session: Session, reset_attempts: bool = False) -> Download:
        """Get a Download by its URL, if it cannot be found create one."""
        if not url:
            raise ValueError('Download must have a URL')

        if download := Download.get_by_url(url, session=session):
            return download

        if self.is_skipped(url):
            if reset_attempts is True:
                self.remove_from_skip_list(url)
            else:
                raise InvalidDownload(
                    f'Refusing to download {url} because it is in the download_manager.yaml skip list')
        download = Download(url=url, status='new')
        session.add(download)
        return download

    @optional_session
    def create_downloads(self, urls: List[str], downloader_name: str, session: Session = None,
                         reset_attempts: bool = False, sub_downloader_name: str = None,
                         destination: str | pathlib.Path = None, tag_names: List[str] = None, settings: dict = None) \
            -> List[Download]:
        """Schedule all URLs for download.  If one cannot be downloaded, none will be added."""
        if not urls or not all(urls):
            raise ValueError(f'Download must have a URL: {urls=}')
        logger.debug(f'Attempting to create {len(urls)} new downloads')

        # Ensure all Tags exist before creating downloads.
        if tag_names:
            with get_db_curs() as curs:
                stmt = 'SELECT name FROM tag WHERE name = ANY(%(tag_names)s)'
                curs.execute(stmt, dict(tag_names=tag_names))
                existing_tag_names = {i[0] for i in curs.fetchall()}
                missing_tag_names = set(tag_names) - existing_tag_names
                if missing_tag_names:
                    raise ValidationError(f'Tag does not exist: {missing_tag_names.pop()}')

        downloads = []
        # Throws an error if no downloader is found.
        self.find_downloader_by_name(downloader_name)

        if destination:
            destination = pathlib.Path(destination) if isinstance(destination, str) else destination
            if not destination.is_absolute():
                destination = get_absolute_media_path(destination)

        for url in urls:
            if url in get_download_manager_config().skip_urls and reset_attempts:
                # User manually entered this download, remove it from the skip list.
                self.remove_from_skip_list(url)
            elif url in get_download_manager_config().skip_urls:
                self.log_warning(f'Skipping {url} because it is in the download_manager.yaml skip list.')
                continue

            download = self.get_or_create_download(url, session, reset_attempts=reset_attempts)
            # Download may have failed, try again.
            download.renew(reset_attempts=reset_attempts)
            download.destination = destination or None
            download.downloader = downloader_name
            download.sub_downloader = sub_downloader_name
            download.tag_names = tag_names or None
            # Preserve existing settings, unless new settings are provided.
            download.settings = settings if settings is not None else download.settings
            if download.frequency and download.settings and (channel_id := download.settings.get('channel_id')):
                # Attach a recurring Channel download to it's Channel.
                download.channel_id = download.channel_id or channel_id

            downloads.append(download)

        logger.debug(f'Created {len(downloads)} new downloads')

        session.flush(downloads)
        try:
            # Start downloading ASAP.
            background_task(self.dispatch_downloads())
            # Save the config now that new Downloads exist.
            save_downloads_config.activate_switch()
        except RuntimeError:
            # Event loop isn't running.  Probably testing?
            if not PYTEST:
                self.log_info(f'Unable to queue downloads after creating {len(downloads)} download(s).')

        return downloads

    @optional_session
    def create_download(self, url: str, downloader_name: str, session: Session = None, reset_attempts: bool = False,
                        sub_downloader_name: str = None, destination: str | pathlib.Path = None,
                        tag_names: List[str] = None, settings: Dict = None) -> Download:
        """Schedule a URL for download.  If the URL failed previously, it may be retried."""
        downloads = self.create_downloads([url], session=session, downloader_name=downloader_name,
                                          reset_attempts=reset_attempts, sub_downloader_name=sub_downloader_name,
                                          destination=destination, tag_names=tag_names, settings=settings)
        return downloads[0]

    @optional_session
    def recurring_download(self, url: str, frequency: int, downloader_name: str, session: Session = None,
                           sub_downloader_name: str = None, reset_attempts: bool = False,
                           destination: str | pathlib.Path = None, tag_names: List[str] = None,
                           settings: Dict = None) -> Download:
        """Schedule a recurring download."""
        if not frequency or not isinstance(frequency, int):
            raise ValueError('Recurring download must have a frequency!')

        from wrolpi.scrape_downloader import ScrapeHTMLDownloader
        if downloader_name == ScrapeHTMLDownloader.name and frequency:
            raise InvalidDownload(f'Cannot schedule recurring download for {downloader_name=}')

        download, = self.create_downloads([url, ], session=session, downloader_name=downloader_name,
                                          reset_attempts=reset_attempts, sub_downloader_name=sub_downloader_name,
                                          destination=destination, tag_names=tag_names, settings=settings)
        download.frequency = frequency

        # Only recurring Downloads can be Channel Downloads.
        from modules.videos.models import Channel
        if channel := Channel.get_by_url(url=download.url, session=session):
            download.channel_id = channel.id

        session.commit()

        return download

    @optional_session
    def update_download(self, id_: int, url: str, downloader: str,
                        destination: str | pathlib.Path = None, tag_names: List[str] = None,
                        sub_downloader: str | None = None, frequency: int = None,
                        settings: Dict = None, session: Session = None) -> Download:
        download = Download.find_by_id(id_, session=session)
        if settings and settings.get('channel_id') and not frequency:
            raise InvalidDownload(f'A once-download cannot be associated with a Channel')
        download.url = url
        download.downloader = downloader
        download.frequency = frequency
        # Preserve existing settings, unless new settings are provided.
        download.settings = settings if settings is not None else download.settings
        # Use provided params even if empty.
        download.destination = destination or None
        download.tag_names = tag_names or None
        download.sub_downloader = sub_downloader or None
        # Remove Channel relationship, if necessary.
        download.channel_id = (settings or dict()).get('channel_id')

        save_downloads_config.activate_switch()

        return download

    @wrol_mode_check
    @optional_session
    async def dispatch_downloads(self, session: Session = None):
        """Dispatch Sanic signals to start downloads.  This only starts as many downloads as the
         SIMULTANEOUS_DOWNLOAD_DOMAINS variable."""
        if not self.can_download:
            # Don't queue downloads when disabled.
            return

        if (domains := len(self.processing_domains)) > SIMULTANEOUS_DOWNLOAD_DOMAINS:
            self.log_debug(
                f'Unable to queue downloads because there are more domains than workers: {domains} >= 4')
            return

        # Find download whose domain isn't already being downloaded.
        new_downloads = list(session.query(Download).filter(
            Download.status == 'new',
            Download.domain not in self.processing_domains,
        ).order_by(
            Download.frequency.is_(None),
            Download.frequency,
            Download.id))
        count = 0
        for download in new_downloads:
            domain = download.domain
            if domain not in self.processing_domains and len(self.processing_domains) < SIMULTANEOUS_DOWNLOAD_DOMAINS:
                self._add_processing_domain(domain)
                context = dict(download_id=download.id, download_url=download.url)
                await api_app.dispatch('wrolpi.download.download', context=context)
                count += 1
        if count:
            self.log_debug(f'Added {count} downloads to queue.')

    async def do_downloads(self):
        """Schedule any downloads that are new.

        Warning: Downloads will still be running even after this returns!  See `wait_for_all_downloads`.
        """
        if not self.can_download:
            return

        try:
            self.renew_recurring_downloads()
        except Exception as e:
            self.log_error(f'Unable to renew downloads!', exc_info=e)

        try:
            self.delete_old_once_downloads()
        except Exception as e:
            self.log_error(f'Unable to delete old downloads!', exc_info=e)

        await self.dispatch_downloads()

    async def wait_for_all_downloads(self, timeout: int = 10):
        """Signals start of all pending Downloads, waits for all Downloads to be processed.

        @param timeout: Give up waiting after this many seconds.
        @raises TimeoutError: If timeout is exceeded.

        @warning: THIS METHOD IS FOR TESTING.
        """
        with timer('wait_for_all_downloads', level='trace'):
            # Use real datetime.now to avoid `fake_now`.
            start = datetime.now()

            while (datetime.now() - start).total_seconds() < timeout:
                # Send out download signals.
                await self.dispatch_downloads()

                # Wait for processes to start.
                await asyncio.sleep(0.1)

                await await_switches()

                # Break out of loop only when all downloads have been processed.
                with get_db_session() as session:
                    statuses = {i.status for i in self.get_downloads(session)}
                    if DownloadStatus.new not in statuses and DownloadStatus.pending not in statuses:
                        # All downloads must be complete/deferred/failed.
                        break
            else:
                raise TimeoutError('Downloads never finished!')

    @staticmethod
    def retry_downloads(reset_attempts: bool = False):
        """Set any incomplete Downloads to `new` so they will be retried.

        @param reset_attempts: Will set `download.attempts` to 0 if True.
        """
        with get_db_curs(commit=True) as curs:
            if reset_attempts:
                stmt = "UPDATE download SET status='new', attempts=0 WHERE status='pending' OR status='deferred'"
            else:
                stmt = "UPDATE download SET status='new' WHERE status='pending' OR status='deferred'"
            curs.execute(stmt)

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

    def renew_recurring_downloads(self):
        """Mark any recurring downloads that are due for download as "new".  Start a download."""
        now_ = now()

        with get_db_session() as session:
            recurring = self.get_recurring_downloads(session)
            renewed_count = 0
            for download in recurring:
                # A new download may not have a `next_download`, create it if necessary.
                download.next_download = download.next_download or self.calculate_next_download(download,
                                                                                                session=session)
                if download.next_download < now_ and download.status not in (
                        DownloadStatus.new, DownloadStatus.pending):
                    download.renew()
                    renewed_count += 1

            if renewed_count:
                self.log_debug(f'Renewed {renewed_count} recurring downloads')
                session.commit()

    @staticmethod
    def get_downloads(session: Session) -> List[Download]:
        downloads = list(session.query(Download).all())
        return downloads

    @optional_session
    def delete_download(self, download_id: int, session: Session = None):
        """Delete a Download.  Returns True if a Download was deleted, otherwise return False."""
        if download := Download.get_by_id(download_id, session=session):
            # This saves the config twice.
            download.delete()
            return True
        return False

    @optional_session
    def restart_download(self, download_id: int, session: Session = None) -> Download:
        """Renews a download and resets its download attempts."""
        download = Download.find_by_id(download_id, session=session)
        download.renew(reset_attempts=True)
        session.commit()

        return download

    def kill_download(self, download_id: int):
        """Fail a Download. If it is pending, kill the Downloader so the download stops."""
        logger.info(f'Killing Download: {download_id}')
        download_manager_data = api_app.shared_ctx.download_manager_data.copy()
        download_manager_data['killed_downloads'] = download_manager_data['killed_downloads'] + [download_id, ]
        api_app.shared_ctx.download_manager_data.update(download_manager_data)

        with get_db_session(commit=True) as session:
            if download := Download.get_by_id(download_id, session=session):
                download.error = 'User stopped this download'
                download.fail()

    @staticmethod
    def unkill_download(download_id: int):
        """Remove a Download from the killed_downloads list.  This allows it to be run again."""
        download_manager_data = api_app.shared_ctx.download_manager_data.copy()
        download_manager_data['killed_downloads'] = \
            [i for i in download_manager_data['killed_downloads'] if i != download_id]
        api_app.shared_ctx.download_manager_data.update(download_manager_data)

    @staticmethod
    def download_is_killed(download_id: int):
        return download_id in api_app.shared_ctx.download_manager_data['killed_downloads']

    FINISHED_STATUSES = (DownloadStatus.complete, DownloadStatus.failed)

    def delete_old_once_downloads(self):
        """Delete all once-downloads that have expired.

        Do not delete downloads that are new, or should be tried again."""
        count = 0
        with get_db_session(commit=True) as session:
            downloads = self.get_once_downloads(session)
            one_month = now() - timedelta(days=30)
            for download in downloads:
                if download.status in self.FINISHED_STATUSES and download.last_successful_download and \
                        download.last_successful_download < one_month:
                    session.delete(download)
                    count += 1
        if count:
            self.log_debug(f'Deleted {count} once downloads')

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
        """Get downloads for the Frontend.  Uses raw SQL for faster result."""
        # Use custom SQL because SQLAlchemy is slow.
        with get_db_curs() as curs:
            stmt = f'''
                SELECT
                    channel_id,
                    destination,
                    downloader,
                    error,
                    frequency,
                    id,
                    last_successful_download,
                    location,
                    next_download,
                    settings,
                    status,
                    sub_downloader,
                    tag_names,
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

            stmt = f'''
                SELECT
                    destination,
                    downloader,
                    error,
                    frequency,
                    id,
                    last_successful_download,
                    location,
                    next_download,
                    settings,
                    status,
                    tag_names,
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

            stmt = '''
                   SELECT COUNT(id) FILTER (
                       WHERE frequency IS NULL
                           AND (status = 'pending' OR status = 'new')
                       )
                   FROM download \
                   '''
            curs.execute(stmt)
            pending_once_downloads = curs.fetchone()[0]

        data = dict(
            recurring_downloads=recurring_downloads,
            once_downloads=once_downloads,
            pending_once_downloads=pending_once_downloads,
        )
        return data

    def get_summary(self) -> dict:
        """
        Get a summary of what Downloads are happening as well as the status of the DownloadManager.
        """
        with get_db_curs() as curs:
            stmt = """
                   SELECT COUNT(*) FILTER (WHERE status = 'pending')    AS pending_downloads,
                          COUNT(*) FILTER (WHERE frequency IS NOT NULL) AS recurring_downloads
                   FROM download \
                   """
            curs.execute(stmt)
            counts = list(map(dict, curs.fetchall()))[0]
        summary = dict(
            pending=counts['pending_downloads'],
            recurring=counts['recurring_downloads'],
            disabled=self.is_disabled,
            stopped=self.is_stopped,
        )
        return summary

    @staticmethod
    @optional_session
    def calculate_next_download(download: Download, session: Session) -> Optional[datetime]:
        """
        If the download is "deferred", download soon.  But, slowly increase the time between attempts.

        If the download is "complete" and the download has a frequency, schedule the download in it's next iteration.
        (Next week, month, etc.)
        """
        if download.is_deferred:
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

    @staticmethod
    def _delete_downloads_q(once: bool = False, status: str = None, returning=Download.id) -> Delete:
        stmt = Download.__table__.delete().returning(returning)
        if once:
            stmt = stmt.where(Download.frequency == None)
        if status:
            stmt = stmt.where(Download.status == status)
        return stmt

    @optional_session
    def delete_completed(self, session: Session) -> List[int]:
        """Delete any completed download records."""
        stmt = self._delete_downloads_q(once=True, status=DownloadStatus.complete)
        deleted_ids = [i for i, in session.execute(stmt).fetchall()]
        session.commit()
        return deleted_ids

    @optional_session
    def delete_failed(self, session: Session):
        """Delete any failed download records."""
        stmt = self._delete_downloads_q(once=True, status=DownloadStatus.failed, returning=Download.url)
        deleted_urls = [i for i, in session.execute(stmt).fetchall()]

        # Add all downloads to permanent skip list.
        self.add_to_skip_list(*deleted_urls)

        session.commit()

    @optional_session
    def delete_once(self, session: Session):
        """Delete all once-download records."""
        stmt = self._delete_downloads_q(once=True)
        deleted_ids = [i for i, in session.execute(stmt).fetchall()]
        session.commit()
        save_downloads_config.activate_switch()
        return deleted_ids

    @staticmethod
    def is_skipped(*urls: str) -> bool:
        if skip_list := get_download_manager_config().skip_urls:
            return all(i in skip_list for i in urls)
        return False

    @staticmethod
    def add_to_skip_list(*urls: str):
        get_download_manager_config().skip_urls = sorted(list(set(get_download_manager_config().skip_urls) | set(urls)))

    @staticmethod
    def remove_from_skip_list(url: str):
        skip_urls = get_download_manager_config().skip_urls
        if url in skip_urls:
            get_download_manager_config().skip_urls = [i for i in get_download_manager_config().skip_urls if i != url]


# The global DownloadManager.  This should be used everywhere!
download_manager = DownloadManager()


@api_app.signal('wrolpi.download.download')
async def signal_download_download(download_id: int, download_url: str):
    """Calls Downloaders based on the download information provided, as well as what is in the DB."""
    from wrolpi.db import get_db_session

    with timer('signal_download_download', 'trace'):
        url = download_url
        download_domain = None

        name = f'download_worker'
        worker_logger = logger.getChild(name)

        try:
            worker_logger.debug(f'Got download {download_id}')

            with get_db_session(commit=True) as session:
                # Mark the download as started in new session so the change is committed.
                download = Download.find_by_id(download_id, session=session)
                download.started()
            download_domain = download.domain

            downloader: Downloader = download.get_downloader()
            if not downloader:
                worker_logger.warning(f'Could not find downloader for {download.downloader=}')

            try_again = True
            try:
                # Create download coroutine.  Wrap it, so it can be canceled.
                if not inspect.iscoroutinefunction(downloader.do_download):
                    raise RuntimeError(f'Coroutine expected from {downloader} do_download method.')
                coro = downloader.do_download(download)
                result = await downloader.cancel_wrapper(coro, download)
            except UnrecoverableDownloadError as e:
                # Download failed and should not be retried.
                worker_logger.warning(f'UnrecoverableDownloadError for {url}', exc_info=e)
                result = DownloadResult(success=False, error=str(traceback.format_exc()))
                try_again = False
            except Exception as e:
                worker_logger.warning(f'Failed to download {url}.  Will be tried again later.', exc_info=e)
                result = DownloadResult(success=False, error=str(traceback.format_exc()))

            # If download has error, and not Internet is available, tell the user!
            if result.error and not flags.have_internet.is_set():
                result.error = f'{result.error}\n\nNo internet available!'

            error_len = len(result.error) if result.error else 0
            worker_logger.debug(
                f'Got success={result.success} from {downloader} download_id={download.id} with {error_len=}')

            with get_db_session(commit=True) as session:
                # Modify the download in a new session because downloads may take a long time.
                download: Download = session.query(Download).filter_by(id=download_id).one()
                # Use a new location if provided, keep the old location if no new location is provided, otherwise
                # clear out an outdated location.
                download.location = result.location or download.location or None
                # Clear any old errors if the download succeeded.
                download.error = result.error if result.error else None
                download.next_download = download_manager.calculate_next_download(download, session)

                urls = download.filter_excluded(result.downloads) if result.downloads else None
                if urls:
                    worker_logger.info(f'Adding {len(result.downloads)} downloads from result of {download.url}')
                    download_manager.create_downloads(urls, session, downloader_name=download.sub_downloader,
                                                      settings=result.settings)

                if try_again is False and not download.frequency:
                    # Only once-downloads can fail.
                    download.fail()
                elif result.success:
                    download.complete()
                else:
                    download.defer()

            # Remove this domain from the running list.
            download_manager._delete_processing_domain(download_domain)
            # Allow the download to resume.
            download_manager.unkill_download(download_id)
            # Save the config now that the Download has finished.
            save_downloads_config.activate_switch()
        except asyncio.CancelledError as e:
            worker_logger.warning('Canceled!', exc_info=e)
            return
        except Exception as e:
            worker_logger.warning(f'Unexpected error', exc_info=e)
        finally:
            # Remove this domain from the running list.
            if download_domain:
                download_manager._delete_processing_domain(download_domain)


@dataclass
class DownloadDictConfig:
    downloader: str
    last_successful_download: str
    next_download: str
    url: str
    frequency: int = None
    settings: dict = None
    status: str = None
    sub_downloader: str = None


@dataclass
class DownloadManagerConfigValidator:
    version: int = None
    downloads: list[DownloadDictConfig] = field(default_factory=list)
    skip_urls: list[str] = field(default_factory=list)


class DownloadManagerConfig(ConfigFile):
    file_name = 'download_manager.yaml'
    default_config = dict(
        downloads=[],
        skip_urls=[],
        version=0,
    )
    validator = DownloadManagerConfigValidator

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

    def dump_config(self, file: pathlib.Path = None, send_events=False, overwrite=False):
        try:
            with get_db_session() as session:
                downloads: Iterable[Download] = session.query(Download).order_by(Download.url)
                new_downloads = []
                for download in downloads:
                    if download.last_successful_download and not download.frequency:
                        # This once-download has completed, do not save it.
                        continue
                    destination = download.destination
                    new_download = dict(
                        destination=str(destination) if destination else None,
                        downloader=download.downloader,
                        frequency=download.frequency,
                        last_successful_download=download.last_successful_download,
                        next_download=download.next_download,
                        settings=download.settings,
                        status=download.status,
                        sub_downloader=download.sub_downloader,
                        tag_names=download.tag_names,
                        url=download.url,
                    )
                    new_downloads.append(new_download)
                get_download_manager_config().update({'downloads': new_downloads}, overwrite=overwrite)
        except Exception as e:
            message = f'Failed to save {self.get_relative_file()} config'
            logger.error(message, exc_info=e)
            if send_events:
                Events.send_config_save_failed(message)

    def import_config(self, file: pathlib.Path = None, send_events=False):
        super().import_config(file)
        with get_db_session(commit=True) as session:
            from modules.zim.lib import zim_download_url_to_name
            from modules.zim.models import ZimSubscription

            try:
                logger.warning('Importing downloads in config')

                downloads_by_url = {i['url']: i for i in get_download_manager_config().downloads}
                existing_downloads: List[Download] = list(session.query(Download))
                for existing in existing_downloads:
                    download = downloads_by_url.pop(existing.url, None)
                    if download:
                        # Download in config already exists, update the DB record.
                        # The config is the source of truth.
                        existing.downloader = download['downloader']
                        existing.destination = download['destination']
                        existing.frequency = download['frequency']
                        existing.last_successful_download = download['last_successful_download']
                        existing.next_download = download['next_download']
                        existing.status = download['status']
                        existing.sub_downloader = download['sub_downloader']
                        existing.settings = download.get('settings') or dict()
                        if 'destination' in existing.settings:
                            # `destination` may be from old config, or from ChannelDownloader.
                            destination = existing.settings.pop('destination')
                            existing.destination = existing.destination or destination
                        if 'tag_names' in existing.settings:
                            # `tag_names` may be from old config, or from ChannelDownloader.
                            tag_names = existing.settings.pop('tag_names')
                            existing.tag_names = existing.tag_names or tag_names
                        existing.flush()
                    else:
                        logger.warning(f'Deleting Download {existing.url} because it is no longer in the config')
                        session.delete(existing)

                for download in downloads_by_url.values():
                    # These downloads are new, import them.
                    download = Download(
                        destination=download['destination'],
                        downloader=download['downloader'],
                        frequency=download['frequency'],
                        last_successful_download=download['last_successful_download'],
                        next_download=download['next_download'],
                        settings=download['settings'] or dict(),
                        status=download['status'],
                        sub_downloader=download['sub_downloader'],
                        tag_names=download['tag_names'],
                        url=(url := download['url']),
                    )
                    session.add(download)
                    logger.info(f'Adding new download {url}')

                session.commit()
                self.successful_import = True
            except Exception as e:
                self.successful_import = False
                message = f'Failed to import {self.file_name}'
                logger.error(message, exc_info=e)
                if send_events:
                    Events.send_config_import_failed(message)
                raise

            try:
                # Claim any Kiwix subscriptions for ZimSubscription(s).
                downloads: List[Download] = session.query(Download)
                need_commit = False
                for download in downloads:
                    if not download.url.startswith('https://download.kiwix.org/') or not download.frequency:
                        # ZimSubscription requires download.kiwix.org AND a frequency.
                        continue

                    name, language = zim_download_url_to_name(download.url)
                    subscription = session.query(ZimSubscription).filter_by(name=name, language=language).one_or_none()
                    if not subscription:
                        subscription = ZimSubscription(name=name, language=language)
                    subscription.change_download(download.url, download.frequency, session=session)
                    session.add(subscription)
                    need_commit = True

                if need_commit:
                    session.commit()
                self.successful_import = True
            except Exception as e:
                self.successful_import = False
                message = 'Failed to restore ZimSubscriptions'
                logger.error(message, exc_info=e)
                if send_events:
                    Events.send_config_import_failed(message)
                raise

            self.successful_import = True


DOWNLOAD_MANAGER_CONFIG: DownloadManagerConfig = DownloadManagerConfig()
TEST_DOWNLOAD_MANAGER_CONFIG: DownloadManagerConfig = None


@contextlib.contextmanager
def downloads_manager_config_context() -> DownloadManagerConfig:
    """Used to create a test config."""
    global TEST_DOWNLOAD_MANAGER_CONFIG
    TEST_DOWNLOAD_MANAGER_CONFIG = DownloadManagerConfig()
    yield TEST_DOWNLOAD_MANAGER_CONFIG
    TEST_DOWNLOAD_MANAGER_CONFIG = None


def get_download_manager_config() -> DownloadManagerConfig:
    global TEST_DOWNLOAD_MANAGER_CONFIG
    if isinstance(TEST_DOWNLOAD_MANAGER_CONFIG, ConfigFile):
        return TEST_DOWNLOAD_MANAGER_CONFIG

    global DOWNLOAD_MANAGER_CONFIG
    return DOWNLOAD_MANAGER_CONFIG


@register_switch_handler('save_downloads_config')
def save_downloads_config():
    """Fetch all Downloads from the DB, save them to the Download Manager Config."""
    get_download_manager_config().dump_config()
    logger.info('save_downloads_config completed')


save_downloads_config: ActivateSwitchMethod


@optional_session
async def import_downloads_config(session: Session):
    """Upsert all Downloads in the Download Manager Config into the DB.

    The config is the source of truth."""
    if not PYTEST and not flags.db_up.is_set():
        logger.warning(f'Refusing to import downloads config when DB is not up.')
        return

    get_download_manager_config().import_config()


def parse_feed(url: str) -> FeedParserDict:
    """Calls `feedparser.parse`, used for testing."""
    return feedparser.parse(url)


class RSSDownloader(Downloader):
    """Downloads an RSS feed and creates new downloads for every unique link in the feed."""
    name = 'rss'
    pretty_name = 'RSS'
    listable = False

    def __repr__(self):
        return '<RSSDownloader>'

    async def do_download(self, download: Download) -> DownloadResult:
        sub_downloader = download_manager.find_downloader_by_name(download.sub_downloader)
        if not sub_downloader:
            raise ValueError(f'Unable to find sub_downloader for {download.url}')

        feed: FeedParserDict = parse_feed(download.url)
        if feed['bozo'] and not self.acceptable_bozo_errors(feed):
            # Feed did not parse
            return DownloadResult(success=False, error='Failed to parse RSS feed')

        if not isinstance(feed, dict) or not feed.get('entries'):
            # RSS parsed but does not have entries.
            return DownloadResult(success=False, error='RSS feed did not have any entries')

        # Apply YT channel to the Download, if not already applied.
        if yt_channel_id := feed.get('feed', dict()).get('yt_channelid'):
            if not (download.location or download.channel_id):
                self.apply_yt_channel(download.id, yt_channel_id)

        # Filter entries using Download.settings.
        entries = self.filter_entries(download, feed['entries'])

        # Filter URL links.
        urls = []
        for idx, entry in enumerate(entries):
            if url := entry.get('link'):
                urls.append(url.strip())
            else:
                logger.warning(f'RSS entry {idx} did not have a link!')

        # Only download new URLs.
        urls = [i for i in urls if i not in [i.url for i in sub_downloader.already_downloaded(*urls)]]
        # Remove skipped URLs before duration checks. (Typically done after this by the download worker).
        urls = [i for i in urls if not download_manager.is_skipped(i)]

        if download.sub_downloader == 'video':  # VideoDownloader
            urls = await self.filter_videos(download, urls)

        logger.info(f'Successfully got {len(urls)} new URLs from RSS {download.url}')

        # Pass settings onto the next Downloader.
        next_download_settings = dict()
        settings = download.settings or dict()
        if i := settings.get('video_resolutions'):
            next_download_settings['video_resolutions'] = i
        if i := settings.get('video_format'):
            next_download_settings['video_format'] = i
        if i := settings.get('destination'):
            next_download_settings['destination'] = i

        result = DownloadResult(
            success=True,
            downloads=urls,
            settings=next_download_settings,
        )
        return result

    @staticmethod
    async def filter_videos(download: Download, urls: list[str]) -> list[str]:
        """Filter Video URLs by comparing the Download's settings."""
        from modules.videos.downloader import fetch_video_duration
        settings = download.settings or dict()
        urls_before = urls.copy()
        maximum_duration: int = settings.get('maximum_duration')
        minimum_duration: int = settings.get('minimum_duration')
        if maximum_duration or minimum_duration:
            # RSS feeds do not have video duration in the XML, so use a cached function to fetch the duration of the
            # linked videos for filtering.
            new_urls = []
            for url in urls:
                # `fetch_video_duration` is cached so can be called frequently.
                try:
                    if maximum_duration and await fetch_video_duration(url) > maximum_duration:
                        continue
                except Exception as e:
                    logger.error(f'Failed to fetch duration: {url}', exc_info=e)
                try:
                    if minimum_duration and await fetch_video_duration(url) < minimum_duration:
                        continue
                except Exception as e:
                    logger.error(f'Failed to fetch duration: {url}', exc_info=e)
                # Download videos even if we fail to fetch their duration.
                new_urls.append(url)
            urls = new_urls
            if urls_before != urls:
                logger.info(f'Filtered videos using min/maximum_duration from {len(urls_before)} to {len(urls)}')

        return urls

    @staticmethod
    def filter_entries(download: Download, entries: List[dict]) -> List[dict]:
        """Filter Feed entries using Download's settings."""
        # Use .lower() to ignore case.
        title_exclude = (download.settings or dict()).get('title_exclude', '')
        title_exclude = [i.lower() for i in title_exclude.split(',') if i]
        title_include = (download.settings or dict()).get('title_include', '')
        title_include = [i.lower() for i in title_include.split(',') if i]

        if title_exclude or title_include:
            filtered_entries = []
            for entry in entries:
                # Filter entries based off title.
                title = entry.get('title', '').lower()
                if title and title_exclude and any(i in title for i in title_exclude):
                    logger.info(f'RSSDownloader skipping excluded entry ({download.url}): {title}')
                    continue
                if title and title_include and not any(i in title for i in title_include):
                    logger.info(f'RSSDownloader skipping non-included entry ({download.url}): {title}')
                    continue
                filtered_entries.append(entry)
            entries = filtered_entries

        return entries

    @staticmethod
    def apply_yt_channel(download_id: int, yt_channel_id: str):
        """Get Channel that matches this Download, apply Channel information to the Download."""
        with get_db_session() as session:
            from modules.videos.models import Channel
            channel = Channel.get_by_source_id(session, f'UC{yt_channel_id}')
            if channel:
                download_ = Download.get_by_id(download_id, session=session)
                download_.channel = channel
                download_.channel_id = channel.id
                download_.location = download_.location or channel.location
                session.commit()

    @staticmethod
    def acceptable_bozo_errors(feed):
        """Feedparser can report some errors, some we can ignore."""
        if 'document declared as' in str(feed['bozo_exception']):
            # Feed's encoding does not match what is declared, this is fine.
            return True
        return False


rss_downloader = RSSDownloader()
