import contextlib
import dataclasses
import html
import pathlib
import re
import traceback
from typing import Generator
from typing import Tuple, Optional

import pytz
from sqlalchemy import or_
from sqlalchemy.orm import Session
from yt_dlp import YoutubeDL

from modules.videos.models import Video
from wrolpi import before_startup, dates, flags
from wrolpi.captions import extract_captions
from wrolpi.common import ConfigFile, limit_concurrent, get_wrolpi_config, extract_domain, \
    escape_file_name, get_media_directory, background_task
from wrolpi.dates import Seconds, from_timestamp
from wrolpi.db import get_db_curs, get_db_session, optional_session
from wrolpi.downloader import Download
from wrolpi.errors import UnknownDirectory
from wrolpi.files.lib import split_path_stem_and_suffix
from wrolpi.vars import YTDLP_CACHE_DIR, PYTEST
from .common import is_valid_poster, convert_image, \
    generate_video_poster, logger, REQUIRED_OPTIONS, ConfigError, \
    get_video_duration
from .errors import UnknownChannel
from .models import Channel

logger = logger.getChild(__name__)

DEFAULT_DOWNLOAD_FREQUENCY = Seconds.week


@dataclasses.dataclass
class VideoInfoJSON:
    channel_source_id: str | None = None
    channel_url: str | None = None
    duration: int | None = None
    title: str | None = None
    url: str | None = None
    view_count: int | None = None
    epoch: int | None = None


def process_video_info_json(video: Video) -> VideoInfoJSON:
    """
    Parse the Video's info json file, return the relevant data.
    """
    video_info_json = VideoInfoJSON()
    if info_json := video.get_info_json():
        title = info_json.get('fulltitle') or info_json.get('title')
        video_info_json.title = html.unescape(title) if title else None

        video_info_json.duration = int(i) if (i := info_json.get('duration')) else None
        video_info_json.view_count = int(i) if (i := info_json.get('view_count')) else None
        video_info_json.url = info_json.get('webpage_url') or info_json.get('url') or None
        video_info_json.channel_source_id = info_json.get('channel_id') or info_json.get('uploader_id') or None
        video_info_json.channel_url = info_json.get('channel_url') or info_json.get('uploader_url') or None
        video_info_json.epoch = int(i) if (i := info_json.get('epoch')) else None

    return video_info_json


EXTRACT_SUBTITLES = False


def validate_video(video: Video, channel_generate_poster: bool):
    """
    Validate a single video.

    A Video is validated when we have attempted to find its: title, duration, view_count, url, caption, size, and
    channel.

    A Video is also valid when it has a JPEG poster, if any.  If no poster can be
    found, it will be generated from the video file.
    """
    info_json_path = video.info_json_path
    json_data_missing = bool(video.file_group.title) and bool(video.file_group.length) and bool(video.view_count) \
                        and bool(video.file_group.url) and bool(video.file_group.download_datetime)
    if info_json_path and json_data_missing is False:
        # These properties can be found in the info json.
        video_info_json = process_video_info_json(video)
        video.file_group.title = video_info_json.title
        video.file_group.length = video_info_json.duration
        video.file_group.url = video_info_json.url
        video.file_group.download_datetime = from_timestamp(video_info_json.epoch) if video_info_json.epoch else None
        # View count will probably be overwritten by more recent data when this Video's Channel is
        # updated.
        video.view_count = video.view_count or video_info_json.view_count

        if video_info_json.channel_source_id or video_info_json.channel_url:
            from modules.videos.channel.lib import get_channel
            try:
                if channel := get_channel(
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
        video.file_group.published_datetime = published_date
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
            video.file_group.length = get_video_duration(video_path)

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
                if not new.is_file():
                    raise FileNotFoundError(f'Failed to convert poster: {new}')
                if old != new:
                    # Only remove the old one if we are not converting in-place.
                    old.unlink(missing_ok=True)
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


class ChannelsConfig(ConfigFile):
    file_name = 'channels.yaml'
    default_config = dict(
        channels=[dict(
            name='WROLPi',
            url='https://www.youtube.com/channel/UC4t8bw1besFTyjW7ZBCOIrw/videos',
            directory='videos/wrolpi',
            download_frequency=604800,
        )],
    )

    @property
    def channels(self) -> dict:
        return self._config['channels']

    @channels.setter
    def channels(self, value: dict):
        self.update({'channels': value})


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


class VideoDownloaderConfig(ConfigFile):
    file_name = 'videos_downloader.yaml'
    default_config = dict(
        continue_dl=True,
        dateafter='19900101',
        file_name_format='%(uploader)s_%(upload_date)s_%(id)s_%(title)s.%(ext)s',
        nooverwrites=True,
        quiet=False,
        writeautomaticsub=True,
        writeinfojson=True,
        writesubtitles=True,
        writethumbnail=True,
        youtube_include_dash_manifest=False,
    )

    @property
    def continue_dl(self) -> bool:
        return self._config['continue_dl']

    @continue_dl.setter
    def continue_dl(self, value: bool):
        self.update({'continue_dl': value})

    @property
    def dateafter(self) -> str:
        return self._config['dateafter']

    @dateafter.setter
    def dateafter(self, value: str):
        self.update({'dateafter': value})

    @property
    def file_name_format(self) -> str:
        return self._config['file_name_format']

    @file_name_format.setter
    def file_name_format(self, value: str):
        self.update({'file_name_format': value})

    @property
    def nooverwrites(self) -> bool:
        return self._config['nooverwrites']

    @nooverwrites.setter
    def nooverwrites(self, value: bool):
        self.update({'nooverwrites': value})

    @property
    def quiet(self) -> bool:
        return self._config['quiet']

    @quiet.setter
    def quiet(self, value: bool):
        self.update({'quiet': value})

    @property
    def writeautomaticsub(self) -> bool:
        return self._config['writeautomaticsub']

    @writeautomaticsub.setter
    def writeautomaticsub(self, value: bool):
        self.update({'writeautomaticsub': value})

    @property
    def writeinfojson(self) -> bool:
        return self._config['writeinfojson']

    @writeinfojson.setter
    def writeinfojson(self, value: bool):
        self.update({'writeinfojson': value})

    @property
    def writesubtitles(self) -> bool:
        return self._config['writesubtitles']

    @writesubtitles.setter
    def writesubtitles(self, value: bool):
        self.update({'writesubtitles': value})

    @property
    def writethumbnail(self) -> bool:
        return self._config['writethumbnail']

    @writethumbnail.setter
    def writethumbnail(self, value: bool):
        self.update({'writethumbnail': value})

    @property
    def youtube_include_dash_manifest(self) -> bool:
        return self._config['youtube_include_dash_manifest']

    @youtube_include_dash_manifest.setter
    def youtube_include_dash_manifest(self, value: bool):
        self.update({'youtube_include_dash_manifest': value})


VIDEO_DOWNLOADER_CONFIG: VideoDownloaderConfig = VideoDownloaderConfig()
TEST_VIDEO_DOWNLOADER_CONFIG: VideoDownloaderConfig = None


def get_downloader_config() -> VideoDownloaderConfig:
    global TEST_VIDEO_DOWNLOADER_CONFIG
    if isinstance(TEST_VIDEO_DOWNLOADER_CONFIG, VideoDownloaderConfig):
        return TEST_VIDEO_DOWNLOADER_CONFIG

    global VIDEO_DOWNLOADER_CONFIG
    return VIDEO_DOWNLOADER_CONFIG


def set_test_downloader_config(enabled: bool):
    global TEST_VIDEO_DOWNLOADER_CONFIG
    TEST_VIDEO_DOWNLOADER_CONFIG = VideoDownloaderConfig() if enabled else None


def get_channels_config_from_db(session: Session) -> dict:
    """Create a dictionary that contains all the Channels from the DB."""
    channels = session.query(Channel).order_by(Channel.directory).all()
    channels = sorted((i.config_view() for i in channels), key=lambda i: i['directory'])
    return dict(channels=channels)


@optional_session()
def save_channels_config(session: Session = None):
    """Get the Channel information from the DB, save it to the config."""
    config = get_channels_config_from_db(session)
    channels_config = get_channels_config()

    if PYTEST and not channels_config:
        logger.warning('Refusing to save channels config because test did not initialize a test config!')
        return

    channels_config.update(config)


channel_import_logger = logger.getChild('channel_import')


async def fetch_channel_source_id(channel_id: int):
    # If we can download from a channel, we must have its source_id.
    try:
        with get_db_session() as session:
            from modules.videos.channel.lib import get_channel
            channel = Channel.find_by_id(channel_id)
            channel.source_id = channel.source_id or get_channel_source_id(channel.url)
            if not channel.source_id:
                channel_import_logger.warning(f'Unable to fetch source_id for {channel.url}')
            else:
                session.commit()
                save_channels_config(session)
    except Exception as e:
        logger.error(f'Failed to get Channel source id of id={channel_id}', exc_info=e)


@before_startup
@limit_concurrent(1)
def import_channels_config():
    """Import channel settings to the DB.  Existing channels will be updated."""
    if PYTEST and not get_channels_config():
        logger.warning('Skipping import_channels_config for this test')
        return

    from .channel.lib import get_channel
    channel_import_logger.info('Importing channels config')
    try:
        config = get_channels_config()
        channels = config.channels
        channel_directories = [i['directory'] for i in channels]
        if len(channel_directories) != len(set(channel_directories)):
            logger.error('Refusing to import channels config because it contains duplicate directories!')
            return
        updated_channel_ids = set()

        with get_db_session(commit=True) as session:
            for data in channels:
                if isinstance(data, str):
                    # Outdated style config.
                    # TODO remove this after beta.
                    data = channels[data]
                # A Channel's directory is saved (in config) relative to the media directory.
                directory = get_media_directory() / data['directory']
                for option in (i for i in REQUIRED_OPTIONS if i not in data):
                    raise ConfigError(f'Channel "{directory}" is required to have "{option}"')

                # Try to find Channel by directory because it is unique.
                channel = Channel.get_by_path(directory, session)
                if not channel:
                    try:
                        # Try to find Channel using other attributes before creating new Channel.
                        channel = get_channel(
                            session,
                            source_id=data.get('source_id'),
                            url=data.get('url'),
                            directory=str(directory),
                            return_dict=False,
                        )
                    except UnknownChannel:
                        # Channel not yet in the DB, add it.
                        channel = Channel(directory=directory)
                        session.add(channel)
                        channel.flush()
                        # TODO refresh the files in the channel.
                        logger.warning(f'Creating new Channel from config {channel}')

                # Copy existing channel data, update all values from the config.  This is necessary to clear out
                # values not in the config.
                full_data = channel.dict()
                full_data.update(data)
                channel.update(full_data)
                updated_channel_ids.add(channel.id)

                if not channel.source_id and channel.url and flags.have_internet.is_set():
                    # If we can download from a channel, we must have its source_id.
                    logger.info(f'Fetching channel source id for {channel}')
                    background_task(fetch_channel_source_id(channel.id))

                channel_import_logger.debug(f'Updated {repr(channel.name)}'
                                            f' url={channel.url}'
                                            f' source_id={channel.source_id}'
                                            f' directory={channel.directory}'
                                            )

        with get_db_session(commit=True) as session:
            # Delete any Channels that were deleted from the config.
            for channel in session.query(Channel):
                if channel.id not in updated_channel_ids:
                    logger.warning(f'Deleting {channel} because it is not in the config.')
                    channel.delete_with_videos()

        # Create any missing Downloads.  Associated Downloads with any necessary Channels.
        link_channel_and_downloads()

    except Exception as e:
        channel_import_logger.warning('Failed to load channels config!', exc_info=e)
        if PYTEST:
            # Do not interrupt startup, only raise during testing.
            raise


@optional_session
def link_channel_and_downloads(session: Session):
    """Create any missing Downloads for any Channel.url/Channel.directory that has a Download.  Associate any Download
    related to a Channel."""
    # Only Downloads with a frequency can be a Channel Download.
    downloads = list(session.query(Download).filter(Download.frequency.isnot(None)).all())
    # Download.url is unique and cannot be null.
    downloads_by_url = {i.url: i for i in downloads}
    # Many Downloads may share the same destination.
    downloads_with_destination = [i for i in downloads if (i.settings or dict()).get('destination')]
    channels = session.query(Channel).all()

    need_commit = False
    for channel in channels:
        directory = str(channel.directory)
        for download in downloads_with_destination:
            if download.settings['destination'] == directory and not download.channel_id:
                download.channel_id = channel.id
                need_commit = True

        download = downloads_by_url.get(channel.url)
        if download and not download.channel_id:
            download.channel_id = channel.id
            need_commit = True

        # Get any Downloads for a Channel's RSS feed.
        rss_url = channel.get_rss_url()
        if rss_url and (download := downloads_by_url.get(rss_url)):
            download.channel_id = channel.id
            need_commit = True

    # Associate any Download which shares a Channel's URL.
    for download in downloads:
        channel = Channel.get_by_url(download.url)
        if channel and not download.channel_id:
            download.channel_id = channel.id
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
            COUNT(v.id) AS "videos",
            -- total videos downloaded over the past week/month/year
            COUNT(v.id) FILTER (WHERE published_datetime >= current_date - interval '1 week') AS "week",
            COUNT(v.id) FILTER (WHERE published_datetime >= current_date - interval '1 month') AS "month",
            COUNT(v.id) FILTER (WHERE published_datetime >= current_date - interval '1 year') AS "year",
            -- sum of all video lengths in seconds
            COALESCE(SUM(fg.length), 0) AS "sum_duration",
            -- sum of all video file sizes
            COALESCE(SUM(fg.size), 0)::BIGINT AS "sum_size",
            -- largest video
            COALESCE(MAX(fg.size), 0) AS "max_size",
            -- Videos may or may not have comments.
            COUNT(v.id) FILTER ( WHERE v.have_comments = TRUE ) AS "have_comments",
            COUNT(v.id) FILTER ( WHERE v.have_comments = FALSE AND v.comments_failed = FALSE
                and fg.censored = false and fg.url is not null) AS "missing_comments",
            COUNT(v.id) FILTER ( WHERE v.comments_failed = TRUE ) AS "failed_comments",
            COUNT(v.id) FILTER ( WHERE fg.censored = TRUE ) as "censored_videos"
        FROM
            video v
            LEFT JOIN file_group fg on v.file_group_id = fg.id
        ''')
        video_stats = dict(curs.fetchone())

        # Get the total videos downloaded every month for the past two years.
        curs.execute('''
        SELECT
            DATE_TRUNC('month', months.a),
            COUNT(video.id)::BIGINT,
            SUM(size)::BIGINT AS "size"
        FROM
            generate_series(
                date_trunc('month', current_date) - interval '2 years',
                date_trunc('month', current_date) - interval '1 month',
                '1 month'::interval) AS months(a),
            video
            LEFT JOIN file_group fg on video.file_group_id = fg.id
        WHERE
            published_datetime >= date_trunc('month', months.a)
            AND published_datetime < date_trunc('month', months.a) + interval '1 month'
            AND published_datetime IS NOT NULL
        GROUP BY
            1
        ORDER BY
            1
        ''')
        monthly_videos = [dict(i) for i in curs.fetchall()]

        historical_stats = dict(monthly_videos=monthly_videos)
        historical_stats['average_count'] = (sum(i['count'] for i in monthly_videos) // len(monthly_videos)) \
            if monthly_videos else 0
        historical_stats['average_size'] = (sum(i['size'] for i in monthly_videos) // len(monthly_videos)) \
            if monthly_videos else 0

        curs.execute('''
        SELECT
            COUNT(c.id) AS "channels",
            COUNT(c.id) FILTER ( WHERE c.tag_id IS NOT NULL ) AS "tagged_channels"
        FROM
            channel c
            LEFT JOIN public.tag t on t.id = c.tag_id
        ''')
        channel_stats = dict(curs.fetchone())
    ret = dict(statistics=dict(
        videos=video_stats,
        channels=channel_stats,
        historical=historical_stats,
    ))
    return ret


NAME_PARSER = re.compile(r'(.*?)_((?:\d+?)|(?:NA))_(?:(.{5,25})_)?(.*)\.'
                         r'(jpg|webp|flv|mp4|part|info\.json|description|webm|..\.srt|..\.vtt)')


def parse_video_file_name(video_path: pathlib.Path) -> \
        Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    A Video's file name can have data in it, this attempts to extract what may be there.

    Example: {channel_name}_{published_datetime}_{source_id}_title{ext}
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
    title = split_path_stem_and_suffix(video_path)[0].strip()
    return None, None, None, title


def find_orphaned_video_files(directory: pathlib.Path) -> Generator[pathlib.Path, None, None]:
    """Finds all files which should be associated with a video file, but a video file does not match their stem.

    Example:
        video1.mp4, video1.info.json  # Video file with info json.
        video2.info.json  # Orphaned video json.
    """
    with get_db_curs() as curs:
        if not directory.is_dir():
            raise UnknownDirectory()

        directory = str(directory).rstrip('/')

        curs.execute(f'''
            SELECT files
            FROM file_group
            WHERE
                mimetype NOT LIKE 'video%'
                AND primary_path LIKE '{directory}/%'
        ''')
        results = (pathlib.Path(j['path']) for i in curs.fetchall() for j in i[0])
        yield from results


def format_videos_destination(channel_name: str = None, channel_tag: str = None, channel_url: str = None) \
        -> pathlib.Path:
    """Return the directory where Videos should be downloaded according to the WROLPi Config.

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
        raise FileNotFoundError(f'Cannot download to the defined "videos_destination"') from e

    videos_destination = get_media_directory() / videos_destination.lstrip('/')

    return videos_destination
