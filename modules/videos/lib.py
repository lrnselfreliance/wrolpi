import contextlib
import dataclasses
import html
import pathlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Generator, Type, List
from typing import Tuple, Optional

import pytz
from sqlalchemy.orm import Session
from yt_dlp import YoutubeDL

from modules.videos.models import Video
from wrolpi import dates, flags
from wrolpi.captions import extract_captions
from wrolpi.common import ConfigFile, extract_domain, logger, \
    escape_file_name, get_media_directory, background_task, Base, get_wrolpi_config, trim_file_name
from wrolpi.dates import Seconds, from_timestamp
from wrolpi.db import get_db_curs, get_db_session
from wrolpi.downloader import Download, download_manager
from wrolpi.errors import UnknownDirectory
from wrolpi.events import Events
from wrolpi.files.lib import split_path_stem_and_suffix
from wrolpi.switches import register_switch_handler, ActivateSwitchMethod
from wrolpi.vars import YTDLP_CACHE_DIR, PYTEST, WROLPI_HOME
from .common import is_valid_poster, convert_image, \
    generate_video_poster, ConfigError, \
    extract_video_duration
from .errors import UnknownChannel
from .models import Channel

logger = logger.getChild(__name__)

DEFAULT_DOWNLOAD_FREQUENCY = Seconds.week

REQUIRED_OPTIONS = ['name', 'directory']


@dataclasses.dataclass
class VideoInfoJSON:
    channel_source_id: str | None = None
    channel_url: str | None = None
    duration: int | None = None
    epoch: int | None = None
    timestamp: datetime | None = None
    title: str | None = None
    upload_date: datetime | None = None
    url: str | None = None
    view_count: int | None = None


def extract_video_info_json(video: Video) -> VideoInfoJSON:
    """
    Parse the Video's info json file, return the relevant data.
    """
    video_info_json = VideoInfoJSON()
    if info_json := video.get_info_json():
        title = info_json.get('fulltitle') or info_json.get('title')
        video_info_json.title = html.unescape(title) if title else None

        upload_date = dates.strpdate(i) if (i := info_json.get('upload_date')) else None
        if upload_date:
            upload_date = upload_date.astimezone(pytz.UTC)
        timestamp = None
        try:
            timestamp = dates.from_timestamp(info_json['timestamp']) if info_json.get('timestamp') else None
        except Exception:
            pass

        video_info_json.channel_source_id = info_json.get('channel_id') or info_json.get('uploader_id') or None
        video_info_json.channel_url = info_json.get('channel_url') or info_json.get('uploader_url') or None
        video_info_json.duration = int(i) if (i := info_json.get('duration')) else None
        video_info_json.epoch = int(i) if (i := info_json.get('epoch')) else None
        video_info_json.timestamp = timestamp
        video_info_json.upload_date = upload_date
        video_info_json.url = info_json.get('webpage_url') or info_json.get('url') or None
        video_info_json.view_count = int(i) if (i := info_json.get('view_count')) else None

    return video_info_json


EXTRACT_SUBTITLES = False


def validate_video(session: Session, video: Video, channel_generate_poster: bool):
    """
    Validate a single video.

    A Video is validated when we have attempted to find its: title, duration, view_count, url, caption, size, and
    channel.

    A Video is also valid when it has a JPEG poster, if any.  If no poster can be
    found, it will be generated from the video file.
    """
    json_published_datetime = None

    if video.info_json_path:
        # These properties can be found in the info json.
        video_info_json = extract_video_info_json(video)
        video.file_group.title = video_info_json.title
        video.file_group.length = video_info_json.duration
        video.file_group.url = video_info_json.url
        json_published_datetime = video.file_group.published_datetime = (
                video_info_json.timestamp  # The exact second the video was published.
                or video_info_json.upload_date  # The day the video was published.
                or video.file_group.published_datetime
        )
        video.file_group.download_datetime = from_timestamp(video_info_json.epoch) if video_info_json.epoch else None
        # View count will probably be overwritten by more recent data when this Video's Channel is
        # updated.
        video.view_count = video.view_count or video_info_json.view_count

        if video_info_json.channel_source_id or video_info_json.channel_url:
            from modules.videos.channel.lib import get_channel
            try:
                if channel := get_channel(
                        session,
                        source_id=video_info_json.channel_source_id,
                        url=video_info_json.channel_url,
                        directory=video.video_path.parent,
                        return_dict=False,
                ):
                    video.channel_id = channel.id
            except UnknownChannel:
                pass

    video_path = video.video_path
    if not video_path:
        logger.error(f'{video} does not have video_path!')

    if video_path and (not video.file_group.title or not video.file_group.published_datetime or not video.source_id):
        # Video is missing things that can be extracted from the video file name.
        # These are the least trusted, so anything already on the video should be trusted.
        _, published_date, source_id, title = parse_video_file_name(video_path)
        published_date = published_date or video.file_group.published_datetime
        if published_date and isinstance(published_date, str):
            published_date = dates.strpdate(published_date)
            if not published_date.tzinfo:
                published_date = published_date.astimezone(pytz.UTC)
        video.file_group.title = video.file_group.title or html.unescape(title)
        # Trust info json upload_date before file name datetime.
        video.file_group.published_datetime = json_published_datetime or published_date
        video.source_id = video.source_id or source_id

    if channel_generate_poster:
        # Try to convert/generate, but keep the old poster if those fail.
        new_poster_path, duration = convert_or_generate_poster(video) or video.poster_path
        if new_poster_path:
            # Poster was created/updated.
            video.file_group.append_files(new_poster_path)
        if duration:
            video.file_group.length = duration

    if video_path and not video.file_group.length:
        # Duration was not retrieved during poster generation.
        if video.ffprobe_json:
            if duration := video.ffprobe_json['format'].get('duration'):
                video.file_group.length = float(duration)
            elif (video_streams := video.get_streams_by_codec_type('video')) and 'duration' in video_streams[0]:
                video.file_group.length = float(video_streams[0]['duration'])
        else:
            # Slowest method.
            video.file_group.length = extract_video_duration(video_path)

    if video_path and not video.caption_paths and video.file_group.d_text and not EXTRACT_SUBTITLES:
        # Caption file was deleted, clear out old captions.
        video.file_group.d_text = None
    elif video_path and not video.file_group.d_text and EXTRACT_SUBTITLES:
        # Captions were not found, extract them from the video.
        video.file_group.d_text = extract_captions(video_path)
    elif video_path and video.caption_paths and not video.file_group.d_text:
        video.file_group.d_text = video.get_caption_text()


def convert_or_generate_poster(video: Video) -> Tuple[Optional[pathlib.Path], Optional[int]]:
    """
    If a Video has a poster, but the poster is invalid, convert it.  If a Video has no poster, generate one from the
    video file.

    Returns None if the poster was not converted, and not generated.
    """
    video_path = video.video_path
    # Modification/generation of poster is enabled for this channel.
    if video.poster_path:
        # Check that the poster is a more universally supported JPEG.
        old: pathlib.Path = video.poster_path
        new = old.with_suffix('.jpg')

        if old != new and new.exists():
            # Destination JPEG already exists (it may have the wrong format).
            old.unlink()
            old = new

        if not is_valid_poster(old):
            # Poster is not valid, convert it and place it in the new location.
            try:
                convert_image(old, new)
                if not new.is_file() or not new.stat().st_size:
                    raise FileNotFoundError(f'Failed to convert poster: {new}')
                logger.info(f'Converted invalid poster {repr(str(old))} to {repr(str(new))}')
                return new, None
            except Exception as e:
                logger.error(f'Failed to convert invalid poster {old} to {new}', exc_info=e)
                return None, None

    if not video.poster_path:
        # Video poster was not discovered, or converted.  Let's generate it.
        try:
            poster_path, duration = generate_video_poster(video_path)
            logger.debug(f'Generated poster for {video}')
            return poster_path, duration
        except Exception as e:
            logger.error(f'Failed to generate poster for {video}', exc_info=e)

    return None, None


@dataclass
class ChannelDictValidator:
    name: str
    directory: str
    download_frequency: int = 604800  # Default to weekly
    url: str = None


@dataclass
class ChannelsConfigValidator:
    version: int = None
    channels: list[ChannelDictValidator] = dataclasses.field(default_factory=list)


class ChannelsConfig(ConfigFile):
    file_name = 'channels.yaml'
    default_config = dict(
        channels=[dict(
            name='WROLPi',
            url='https://www.youtube.com/channel/UC4t8bw1besFTyjW7ZBCOIrw/videos',
            directory='videos/wrolpi',
            download_frequency=604800,
        )],
        version=0,
    )
    validator = ChannelsConfigValidator

    @property
    def channels(self) -> dict:
        return self._config['channels']

    @channels.setter
    def channels(self, value: dict):
        self.update({'channels': value})

    def import_config(self, file: pathlib.Path = None, send_events=False):
        """Import channels from config file into database using batch operations."""
        file = file or self.get_file()

        # If config file doesn't exist, mark import as successful (nothing to import)
        if not file.is_file():
            channel_import_logger.info('No channels config file, skipping import')
            self.successful_import = True
            return

        super().import_config()
        try:
            channels = self.channels
            # Empty channels list = never delete DB records
            if not channels:
                channel_import_logger.info('No channels in config, preserving existing DB channels')
                self.successful_import = True
                return

            channel_directories = [i['directory'] for i in channels]
            if len(channel_directories) != len(set(channel_directories)):
                raise RuntimeError('Refusing to import channels config because it contains duplicate directories!')

            # Validate all channels have required options
            for data in channels:
                directory = get_media_directory() / data['directory']
                for option in (i for i in REQUIRED_OPTIONS if i not in data):
                    raise ConfigError(f'Channel "{directory}" is required to have "{option}"')

            updated_channel_ids = set()

            with get_db_session(commit=True) as session:
                # Prepare data with kind='channel' for all entries
                channel_data_list = []
                for data in channels:
                    data = data.copy()
                    data['kind'] = 'channel'
                    channel_data_list.append(data)

                # Batch create/update Collections
                from wrolpi.collections import Collection
                collections = Collection.batch_from_config(session, channel_data_list)

                # Pre-fetch existing Channels by collection_id in ONE query
                collection_ids = [c.id for c in collections]
                existing_channels_list = session.query(Channel).filter(
                    Channel.collection_id.in_(collection_ids)
                ).all()
                existing_channels = {ch.collection_id: ch for ch in existing_channels_list}

                # Pre-fetch all tags for channel update in ONE query
                tag_names = {d.get('tag_name') for d in channels if d.get('tag_name')}
                tags_by_name = {}
                if tag_names:
                    from wrolpi.tags import Tag
                    tags = session.query(Tag).filter(Tag.name.in_(tag_names)).all()
                    tags_by_name = {t.name: t for t in tags}

                # Pre-fetch existing downloads for update in ONE query
                download_urls = set()
                for data in channels:
                    for dl in data.get('downloads', []):
                        if isinstance(dl, dict):
                            download_urls.add(dl['url'])
                existing_downloads = {}
                if download_urls:
                    from wrolpi.downloader import Download
                    downloads = session.query(Download).filter(Download.url.in_(download_urls)).all()
                    existing_downloads = {d.url: d for d in downloads}

                # Process channels
                new_channels = []
                for collection, data in zip(collections, channel_data_list):
                    channel = existing_channels.get(collection.id)

                    if not channel:
                        # Create new Channel
                        channel = Channel(
                            collection_id=collection.id,
                            url=data.get('url'),
                            source_id=data.get('source_id'),
                        )
                        new_channels.append(channel)
                        existing_channels[collection.id] = channel

                # Batch add new channels
                if new_channels:
                    session.add_all(new_channels)
                    session.flush()

                # Now update all channels (both new and existing)
                for collection, data in zip(collections, channel_data_list):
                    channel = existing_channels[collection.id]
                    # Call batch_update with pre-fetched data
                    channel.batch_update(data, tags_by_name, existing_downloads)
                    updated_channel_ids.add(channel.id)

                    # Background task for missing source_id
                    if not channel.source_id and channel.url and flags.have_internet.is_set():
                        if download_manager.can_download and channel.download_missing_data:
                            channel_import_logger.info(f'Fetching channel source id for {channel}')
                            background_task(fetch_channel_source_id(channel.id))

                    channel_import_logger.debug(f'Updated {repr(channel.name)}'
                                                f' url={channel.url}'
                                                f' source_id={channel.source_id}'
                                                f' directory={channel.directory}'
                                                )

            with get_db_session(commit=True) as session:
                # Delete any Channels that were deleted from the config, along with their Collections.
                orphaned_collection_ids = []
                for channel in session.query(Channel):
                    if channel.id not in updated_channel_ids:
                        logger.warning(f'Deleting {channel} because it is not in the config.')
                        orphaned_collection_ids.append(channel.collection_id)
                        channel.delete_with_videos()

                # Delete orphaned Collections (kind='channel') that no longer have a Channel.
                # This prevents Collections from appearing in the UI with null channel_id.
                from wrolpi.collections import Collection
                for collection_id in orphaned_collection_ids:
                    collection = session.query(Collection).filter_by(id=collection_id).one_or_none()
                    if collection:
                        logger.warning(f'Deleting orphaned Collection {collection.name} (id={collection.id})')
                        session.delete(collection)

            # Also clean up any pre-existing orphaned Collections (kind='channel')
            # that have no associated Channel. This handles orphans created before
            # this cleanup logic was added.
            with get_db_session(commit=True) as session:
                from wrolpi.collections import Collection
                # Find all Collections with kind='channel' that no Channel references
                orphaned_collections = session.query(Collection).outerjoin(
                    Channel, Channel.collection_id == Collection.id
                ).filter(
                    Collection.kind == 'channel',
                    Channel.id.is_(None)
                ).all()

                for collection in orphaned_collections:
                    logger.warning(f'Deleting pre-existing orphaned Collection {collection.name} (id={collection.id})')
                    session.delete(collection)

            # Assign Videos to Channels using bulk SQL
            from modules.videos import claim_videos_for_channels
            claim_videos_for_channels(list(updated_channel_ids))

            # Create any missing Downloads. Associate Downloads with any necessary Channels.
            with get_db_session() as session:
                link_channel_and_downloads(session)

            self.successful_import = True
        except Exception as e:
            self.successful_import = False
            message = f'Failed to import {self.get_relative_file()} config!'
            if send_events:
                channel_import_logger.warning(message, exc_info=e)
                Events.send_config_import_failed(message)
            raise

    def dump_config(self, file: pathlib.Path = None, send_events=False, overwrite=False):
        """Dump all channels from database to config file."""
        from wrolpi.collections import Collection
        channel_import_logger.info('Dumping channels to config')

        with get_db_session() as session:
            # Get all channels, ordered by collection name
            channels = session.query(Channel).join(Collection).order_by(Collection.name).all()

            # Use config_view to export each channel
            channels_data = [channel.config_view() for channel in channels]

            self._config['channels'] = channels_data

        channel_import_logger.info(f'Dumping {len(channels_data)} channels to config')
        self.save(file, send_events, overwrite)


CHANNELS_CONFIG: ChannelsConfig = ChannelsConfig()
TEST_CHANNELS_CONFIG: ChannelsConfig = None


def get_channels_config() -> ChannelsConfig:
    global TEST_CHANNELS_CONFIG
    if PYTEST and not TEST_CHANNELS_CONFIG:
        logger.warning('Test did not initialize the channels config')
        return

    if TEST_CHANNELS_CONFIG:
        return TEST_CHANNELS_CONFIG

    global CHANNELS_CONFIG
    return CHANNELS_CONFIG


@contextlib.contextmanager
def set_test_channels_config():
    global TEST_CHANNELS_CONFIG
    TEST_CHANNELS_CONFIG = ChannelsConfig()
    TEST_CHANNELS_CONFIG.initialize()
    yield TEST_CHANNELS_CONFIG
    TEST_CHANNELS_CONFIG = None


@dataclass
class VideoDownloaderConfigYtDlpOptionsValidator:
    continue_dl: bool
    file_name_format: str
    nooverwrites: bool
    quiet: bool
    merge_output_format: str
    writeautomaticsub: bool
    writeinfojson: bool
    writesubtitles: bool
    writethumbnail: bool
    youtube_include_dash_manifest: bool

    def __post_init__(self):
        from modules.videos.downloader import preview_filename
        try:
            preview_filename(self.file_name_format)
        except Exception as e:
            raise ValueError(f'file_name_format is invalid: {str(e)}')


@dataclass
class VideoDownloaderConfigValidator:
    video_resolutions: List[str] = field(default_factory=lambda: ['1080p', '720p', '480p', 'maximum'])
    version: int = None
    yt_dlp_options: VideoDownloaderConfigYtDlpOptionsValidator = field(default_factory=dict)
    yt_dlp_extra_args: str = ''
    always_use_browser_profile: bool = False
    browser_profile: str = ''

    def __post_init__(self):
        allowed_fields = {i.name for i in dataclasses.fields(VideoDownloaderConfigYtDlpOptionsValidator)}
        yt_dlp_options = {k: v for k, v in dict(self.yt_dlp_options).items() if k in allowed_fields}
        VideoDownloaderConfigYtDlpOptionsValidator(**yt_dlp_options)
        self.yt_dlp_options = yt_dlp_options


class VideoDownloaderConfig(ConfigFile):
    file_name = 'videos_downloader.yaml'
    default_config = dict(
        video_resolutions=['1080p', '720p', '480p', 'maximum'],
        version=0,
        yt_dlp_options=dict(
            continue_dl=True,
            file_name_format='%(uploader)s_%(upload_date)s_%(id)s_%(title)s.%(ext)s',
            merge_output_format='mp4',
            nooverwrites=True,
            quiet=False,
            writeautomaticsub=True,
            writeinfojson=True,
            writesubtitles=True,
            writethumbnail=True,
            youtube_include_dash_manifest=False,
        ),
        yt_dlp_extra_args='',
        always_use_browser_profile=False,
        browser_profile='',
    )
    validator = VideoDownloaderConfigValidator

    @property
    def continue_dl(self) -> bool:
        return self._config['yt_dlp_options']['continue_dl']

    @property
    def video_resolutions(self) -> List[str]:
        return self._config['video_resolutions']

    @video_resolutions.setter
    def video_resolutions(self, value: List[str]):
        self.update({'video_resolutions': value})

    @property
    def file_name_format(self) -> str:
        return self._config['yt_dlp_options']['file_name_format']

    @property
    def nooverwrites(self) -> bool:
        return self._config['yt_dlp_options']['nooverwrites']

    @property
    def merge_output_format(self) -> bool:
        return self._config['yt_dlp_options']['merge_output_format']

    @property
    def quiet(self) -> bool:
        return self._config['yt_dlp_options']['quiet']

    @property
    def writeautomaticsub(self) -> bool:
        return self._config['yt_dlp_options']['writeautomaticsub']

    @property
    def writeinfojson(self) -> bool:
        return self._config['yt_dlp_options']['writeinfojson']

    @property
    def writesubtitles(self) -> bool:
        return self._config['yt_dlp_options']['writesubtitles']

    @property
    def writethumbnail(self) -> bool:
        return self._config['yt_dlp_options']['writethumbnail']

    @property
    def youtube_include_dash_manifest(self) -> bool:
        return self._config['yt_dlp_options']['youtube_include_dash_manifest']

    @property
    def yt_dlp_options(self) -> dict:
        return self._config['yt_dlp_options']

    @yt_dlp_options.setter
    def yt_dlp_options(self, value: dict):
        self.update({'yt_dlp_options': value})

    @property
    def yt_dlp_extra_args(self) -> str:
        return self._config['yt_dlp_extra_args']

    @yt_dlp_extra_args.setter
    def yt_dlp_extra_args(self, value: str):
        self.update({**self._config, 'yt_dlp_extra_args': value})

    @property
    def browser_profile(self) -> str:
        return self._config['browser_profile']

    @browser_profile.setter
    def browser_profile(self, value: str):
        self.update({**self._config, 'browser_profile': value})

    @property
    def always_use_browser_profile(self) -> bool:
        return self._config['always_use_browser_profile']

    @always_use_browser_profile.setter
    def always_use_browser_profile(self, value: bool):
        self.update({**self._config, 'always_use_browser_profile': value})

    def import_config(self, file: pathlib.Path = None, send_events=False):
        super().import_config(file, send_events)
        self.successful_import = True


VIDEOS_DOWNLOADER_CONFIG: VideoDownloaderConfig = VideoDownloaderConfig()
TEST_VIDEOS_DOWNLOADER_CONFIG: VideoDownloaderConfig = None


def get_videos_downloader_config() -> VideoDownloaderConfig:
    global TEST_VIDEOS_DOWNLOADER_CONFIG
    if isinstance(TEST_VIDEOS_DOWNLOADER_CONFIG, VideoDownloaderConfig):
        return TEST_VIDEOS_DOWNLOADER_CONFIG

    global VIDEOS_DOWNLOADER_CONFIG
    return VIDEOS_DOWNLOADER_CONFIG


def set_test_downloader_config(enabled: bool):
    global TEST_VIDEOS_DOWNLOADER_CONFIG
    TEST_VIDEOS_DOWNLOADER_CONFIG = VideoDownloaderConfig() if enabled else None


def get_channels_config_from_db(session: Session) -> dict:
    """Create a dictionary that contains all the Channels from the DB."""
    from wrolpi.collections import Collection
    channels = session.query(Channel).join(Collection).order_by(Collection.directory).all()
    channels = sorted((i.config_view() for i in channels), key=lambda i: i['directory'] if i['directory'] else '')
    return dict(channels=channels)


@register_switch_handler('save_channels_config')
def save_channels_config():
    """Get the Channel information from the DB, save it to the config."""
    with get_db_session() as session:
        config = get_channels_config_from_db(session)
        channels_config = get_channels_config()

    if PYTEST and not channels_config:
        logger.warning('Refusing to save channels config because test did not initialize a test config!')
        return

    channels_config.update(config)
    logger.info('save_channels_config completed')


save_channels_config: ActivateSwitchMethod

channel_import_logger = logger.getChild('channel_import')


async def fetch_channel_source_id(channel_id: int):
    # If we can download from a channel, we must have its source_id.
    try:
        with get_db_session() as session:
            from modules.videos.channel.lib import get_channel
            channel = Channel.find_by_id(session, channel_id)
            channel.source_id = channel.source_id or get_channel_source_id(channel.url)
            if not channel.source_id:
                channel_import_logger.warning(f'Unable to fetch source_id for {channel.url}')
            else:
                session.commit()
                save_channels_config.activate_switch()
    except Exception as e:
        logger.error(f'Failed to get Channel source id of id={channel_id}', exc_info=e)


def import_channels_config():
    """Import channel settings to the DB.  Existing channels will be updated."""
    if PYTEST and not get_channels_config():
        logger.warning('Skipping import_channels_config for this test')
        return

    channel_import_logger.info('Importing channels config')
    get_channels_config().import_config()
    channel_import_logger.info('Importing channels config completed')


def link_channel_and_downloads(session: Session, channel_: Type[Base] = Channel, download_: Type[Base] = Download):
    """Associate any Download related to a Channel via its Collection.

    Downloads are linked to Collections (via collection_id) rather than directly to Channels.
    This function finds Channels and links their Downloads to the Channel's Collection.
    """
    # Only Downloads with a frequency can be a Collection Download.
    downloads = list(session.query(download_).filter(download_.frequency.isnot(None)).all())
    # Download.url is unique and cannot be null.
    downloads_by_url = {i.url: i for i in downloads}
    # Many Downloads may share the same destination.
    downloads_with_destination = [i for i in downloads if (i.settings or dict()).get('destination')]
    channels = session.query(channel_).all()

    need_commit = False
    for channel in channels:
        directory = str(channel.directory)
        for download in downloads_with_destination:
            if download.settings['destination'] == directory and not download.collection_id:
                download.collection_id = channel.collection_id
                need_commit = True

        download = downloads_by_url.get(channel.url)
        if download and not download.collection_id:
            download.collection_id = channel.collection_id
            need_commit = True

        # Get any Downloads for a Channel's RSS feed.
        rss_url = channel.get_rss_url()
        if rss_url and (download := downloads_by_url.get(rss_url)):
            if not download.collection_id:
                download.collection_id = channel.collection_id
                need_commit = True

    # Associate any Download which shares a Channel's URL.
    for download in downloads:
        channel = channel_.get_by_url(session, download.url)
        if channel and not download.collection_id:
            download.collection_id = channel.collection_id
            need_commit = True

    if need_commit:
        session.commit()


YDL = YoutubeDL(dict(cachedir=YTDLP_CACHE_DIR))
ydl_logger = YDL.params['logger'] = logger.getChild('youtube-dl')
YDL.add_default_info_extractors()


def get_channel_source_id(url: str) -> str:
    channel_info = YDL.extract_info(url, download=False, process=False)
    return channel_info.get('channel_id') or channel_info['uploader_id']


async def get_statistics():
    with get_db_curs() as curs:
        curs.execute('''
                     SELECT
                         -- total videos
                         COUNT(v.id)                                                                        AS "videos",
                         -- total videos downloaded over the past week/month/year
                         COUNT(v.id) FILTER (WHERE published_datetime >= current_date - interval '1 week')  AS "week",
                         COUNT(v.id) FILTER (WHERE published_datetime >= current_date - interval '1 month') AS "month",
                         COUNT(v.id) FILTER (WHERE published_datetime >= current_date - interval '1 year')  AS "year",
                         -- sum of all video lengths in seconds
                         COALESCE(SUM(fg.length), 0)                                                        AS "sum_duration",
                         -- sum of all video file sizes
                         COALESCE(SUM(fg.size), 0)::BIGINT                                                  AS "sum_size",
                         -- largest video
                         COALESCE(MAX(fg.size), 0)                                                          AS "max_size",
                         -- Videos may or may not have comments.
                         COUNT(v.id) FILTER ( WHERE v.have_comments = TRUE )                                AS "have_comments",
                         COUNT(v.id) FILTER ( WHERE v.have_comments = FALSE AND v.comments_failed = FALSE
                             and fg.censored = false and
                                                    fg.url is not null)                                     AS "missing_comments",
                         COUNT(v.id) FILTER ( WHERE v.comments_failed = TRUE )                              AS "failed_comments",
                         COUNT(v.id) FILTER ( WHERE fg.censored = TRUE )                                    as "censored_videos"
                     FROM video v
                              LEFT JOIN file_group fg on v.file_group_id = fg.id
                     ''')
        video_stats = dict(curs.fetchone())

        # Get the total videos downloaded every month for the past two years.
        curs.execute('''
                     SELECT DATE_TRUNC('month', months.a),
                            COUNT(video.id)::BIGINT,
                            SUM(size)::BIGINT AS "size"
                     FROM generate_series(
                                  date_trunc('month', current_date) - interval '2 years',
                                  date_trunc('month', current_date) - interval '1 month',
                                  '1 month'::interval) AS months(a),
                          video
                              LEFT JOIN file_group fg on video.file_group_id = fg.id
                     WHERE published_datetime >= date_trunc('month', months.a)
                       AND published_datetime < date_trunc('month', months.a) + interval '1 month'
                       AND published_datetime IS NOT NULL
                     GROUP BY 1
                     ORDER BY 1
                     ''')
        monthly_videos = [dict(i) for i in curs.fetchall()]

        historical_stats = dict(monthly_videos=monthly_videos)
        historical_stats['average_count'] = (sum(i['count'] for i in monthly_videos) // len(monthly_videos)) \
            if monthly_videos else 0
        historical_stats['average_size'] = (sum(i['size'] for i in monthly_videos) // len(monthly_videos)) \
            if monthly_videos else 0

        curs.execute('''
                     SELECT COUNT(c.id)                                         AS "channels",
                            COUNT(c.id) FILTER ( WHERE col.tag_id IS NOT NULL ) AS "tagged_channels"
                     FROM channel c
                              LEFT JOIN collection col on col.id = c.collection_id
                              LEFT JOIN public.tag t on t.id = col.tag_id
                     ''')
        channel_stats = dict(curs.fetchone())
    ret = dict(statistics=dict(
        videos=video_stats,
        channels=channel_stats,
        historical=historical_stats,
    ))
    return ret


NAME_PARSER = re.compile(
    r'(?:(.*?)_)?((?:\d+?)|(?:NA))_(?:(.{5,25})_)?(.*)'
    r'\.(jpg|webp|flv|mp4|part|info\.json|description|webm|..\.srt|..\.vtt)',  # the file suffix
    re.IGNORECASE)


def parse_video_file_name(video_path: pathlib.Path) -> \
        Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    A Video's file name can have data in it, this attempts to extract what may be there.

    {published_date} is assumed to always be %Y%m%d

    Examples:
        NA_{published_date}_{source_id}_{title}{ext}
        {channel_name}_NA_{source_id}_{title}{ext}
        {channel_name}_{published_date}_{source_id}_{title}{ext}  # Typical name format from WROLPi.
        {published_date}_{title}{ext}
        {title}{ext}
    """
    video_str = str(video_path)
    if match := NAME_PARSER.match(video_str):
        channel, date, source_id, title, _ = match.groups()

        channel = None if channel == 'NA' else channel
        date = None if date == 'NA' else date

        title = title.strip()
        if date == 'NA':
            return channel, None, source_id, title
        if date is None or (len(date) == 8 and date.isdigit()):
            return channel, date, source_id, title

    # Return the stem as a last resort
    title, _ = split_path_stem_and_suffix(video_path)
    return None, None, None, title.strip()


def find_orphaned_video_files(directory: pathlib.Path) -> Generator[pathlib.Path, None, None]:
    """Finds all files which should be associated with a video file, but a video file does not match their stem.

    Example:
        video1.mp4, video1.info.json  # Video file with info json.
        video2.info.json  # Orphaned video json.
    """
    with get_db_curs() as curs:
        if not directory.is_dir():
            raise UnknownDirectory()

        directory_str = str(directory).rstrip('/')

        # Query returns directory and files - files may contain relative or absolute paths
        # Use indexed directory column for efficient lookup
        curs.execute(f'''
            SELECT directory, files
            FROM file_group
            WHERE
                mimetype NOT LIKE 'video%%'
                AND (directory = '{directory_str}' OR directory LIKE '{directory_str}/%%')
        ''')
        for row in curs.fetchall():
            fg_directory = pathlib.Path(row[0]) if row[0] else None
            for file_info in row[1]:
                path = pathlib.Path(file_info['path'])
                if not path.is_absolute() and fg_directory:
                    # Resolve relative path using directory
                    path = fg_directory / path
                yield path


def format_videos_destination(channel_name: str = None, channel_tag: str = None, channel_url: str = None) \
        -> pathlib.Path:
    """Return the directory where Videos should be downloaded according to the WROLPi Config.

    Note: When you have a Collection object, prefer using Collection.format_destination()
    or Collection.get_or_set_directory() instead, as they provide unified behavior
    across both channel and domain collections.

    @warning: Directory may or may not exist."""
    videos_destination = get_wrolpi_config().videos_destination

    channel_domain = ''
    if channel_url:
        try:
            channel_domain = extract_domain(channel_url)
        except Exception as e:
            logger.error(f'Failed to extract domain from Channel URL: {channel_url}', exc_info=e)
            if PYTEST:
                raise

    if channel_name and not isinstance(channel_name, str):
        raise RuntimeError('channel name must be string')
    if channel_tag and not isinstance(channel_tag, str):
        raise RuntimeError('channel tag must be string')

    name = escape_file_name(channel_name) if channel_name else ''
    variables = dict(
        channel_name=name,
        channel_tag=channel_tag or '',
        channel_domain=channel_domain,
    )

    try:
        videos_destination = videos_destination % variables
    except KeyError as e:
        msg = f'Cannot download to the "videos_destination" from Settings: {videos_destination}'
        raise FileNotFoundError(msg) from e

    videos_destination = get_media_directory() / videos_destination.lstrip('/')

    return videos_destination


def get_browser_profiles(home: pathlib.Path = WROLPI_HOME) -> dict:
    """Searches the provided home directory for Chromium and Firefox profiles."""
    logger.debug(f'Searching for browser profiles in {home}')

    profiles = dict(chromium_profiles=[], firefox_profiles=[])

    chromium_directory = home / '.config/chromium'
    default_chromium_profile = chromium_directory / 'Default'

    if default_chromium_profile.is_dir():
        profiles['chromium_profiles'].append(default_chromium_profile)
    chromium_profiles = chromium_directory.glob('Profile *')
    for chromium_profile in chromium_profiles:
        if chromium_profile.is_dir():
            profiles['chromium_profiles'].append(chromium_profile)

    firefox_profiles_directory = home / '.mozilla/firefox'
    firefox_profiles_file = firefox_profiles_directory / 'profiles.ini'
    if firefox_profiles_file.is_file():
        # Read the profile.ini and get the default profile path.
        firefox_profiles_file = firefox_profiles_file.read_text()

        default_firefox_profile = re.findall(r'Default=(.*)', firefox_profiles_file)
        if default_firefox_profile:
            default_firefox_profile = firefox_profiles_directory / default_firefox_profile[0]

            if default_firefox_profile.is_dir():
                profiles['firefox_profiles'].append(default_firefox_profile)

    return profiles


def browser_profile_to_yt_dlp_arg(profile: pathlib.Path) -> str:
    """Takes a Path and returns a string that can be used as a yt-dlp `--cookies-from-browser` argument."""
    *_, browser, profile = str(profile).split('/')
    return f'{browser}:{profile}'


def format_video_filename(
        video: Video,
        file_name_format: str = None,
) -> str:
    """Single source of truth for video filenames.

    Formats a video filename using the configured file_name_format template.
    Used by both the video downloader (initial download) and collection reorganization.

    Args:
        video: Video model with metadata (upload_date, uploader, title, source_id)
        file_name_format: Optional override, defaults to config value

    Returns:
        Formatted filename (may include subdirectory path like "2025/01/video.mp4")

    Example:
        With format '%(upload_year)s/%(upload_month)s/%(uploader)s_%(upload_date)s_%(id)s_%(title)s.%(ext)s':
        Returns '2025/01/WROLPi_20250115_abc123_My Video Title.mp4'
    """
    from modules.videos.downloader import convert_wrolpi_filename_format

    config = get_videos_downloader_config()
    template = file_name_format or config.file_name_format

    # Get metadata from video
    file_group = video.file_group
    info_json = video.get_info_json() or {}

    # Extract upload date info
    upload_date = file_group.published_datetime
    if not upload_date and info_json.get('upload_date'):
        upload_date = dates.strpdate(info_json['upload_date'])

    # Build variables dict matching yt-dlp's expected variables
    # Use info_json if available, fall back to derived values
    uploader = info_json.get('uploader') or info_json.get('channel') or ''
    title = file_group.title or info_json.get('title') or info_json.get('fulltitle') or 'untitled'
    source_id = video.source_id or info_json.get('id') or ''

    # Get video file extension
    video_path = video.video_path
    ext = video_path.suffix.lstrip('.') if video_path else config.merge_output_format or 'mp4'

    variables = dict(
        uploader=escape_file_name(uploader) if uploader else '',
        channel=escape_file_name(uploader) if uploader else '',  # Alias
        upload_date=upload_date.strftime('%Y%m%d') if upload_date else '',
        id=source_id,
        title=escape_file_name(title) if title else 'untitled',
        ext=ext,
        # WROLPi-specific variables for subdirectory organization
        upload_year=str(upload_date.year) if upload_date else '',
        upload_month=f'{upload_date.month:02d}' if upload_date else '',
    )

    # Convert WROLPi-specific variables to yt-dlp syntax then apply
    # (This handles %(upload_year)s -> %(upload_date>%Y)s conversion)
    converted_template = convert_wrolpi_filename_format(template)

    # For the converted variables (like %(upload_date>%Y)s), we need to add them too
    variables['upload_date>%Y'] = str(upload_date.year) if upload_date else ''
    variables['upload_date>%m'] = f'{upload_date.month:02d}' if upload_date else ''

    try:
        result = converted_template % variables
        # Trim the filename portion if it's too long (may include subdirectory paths)
        if '/' in result:
            # Has subdirectories - only trim the filename part
            parts = result.rsplit('/', 1)
            subdir = parts[0]
            filename = trim_file_name(parts[1])
            return f'{subdir}/{filename}'
        else:
            return trim_file_name(result)
    except KeyError as e:
        logger.error(f'Invalid variable in video file_name_format: {e}')
        # Fallback to a simple format
        fallback_title = escape_file_name(title) if title else 'untitled'
        return trim_file_name(f'{fallback_title}.{ext}')
