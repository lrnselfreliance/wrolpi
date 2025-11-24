#! /usr/bin/env python3
import copy
import json
import logging
import os.path
import pathlib
import re
import sys
import traceback
from abc import ABC
from datetime import timedelta
from typing import Tuple, List, Dict, Optional

import cachetools
import yt_dlp.utils
from cachetools.keys import hashkey
from sqlalchemy.orm import Session
from yt_dlp import YoutubeDL, DownloadError
from yt_dlp.extractor import YoutubeTabIE  # noqa

from wrolpi.cmd import YT_DLP_BIN
from wrolpi.common import logger, get_media_directory, escape_file_name, resolve_generators, background_task, \
    trim_file_name, cached_multiprocessing_result, get_absolute_media_path
from wrolpi.dates import now
from wrolpi.db import get_db_session
from wrolpi.db import optional_session
from wrolpi.downloader import Downloader, Download, DownloadResult
from wrolpi.errors import UnrecoverableDownloadError
from wrolpi.files.lib import glob_shared_stem, split_path_stem_and_suffix
from wrolpi.files.models import FileGroup
from wrolpi.vars import PYTEST, YTDLP_CACHE_DIR
from .channel.lib import create_channel, get_channel
from .common import get_no_channel_directory, update_view_counts_and_censored, \
    ffmpeg_video_complete
from .errors import UnknownChannel
from .lib import get_videos_downloader_config, YDL, ydl_logger, format_videos_destination, browser_profile_to_yt_dlp_arg
from .models import Video, Channel
from .normalize_video_url import normalize_video_url
from .schema import ChannelPostRequest
from .video.lib import download_video_info_json

logger = logger.getChild(__name__)

VIDEO_RESOLUTION_MAP = {
    '360p': [
        '134+bestaudio', '230+bestaudio', 'mp4-360p', 'res:360',
        'hls-175+bestaudio',  # 360p avc1 + best audio
        '396+bestaudio', '243+bestaudio',  # Vertical
        'hls-655+bestaudio', 'hls-655',
        'bestvideo[height=360]+bestaudio/best[height=360]',
    ],
    '480p': [
        '135+bestaudio', '231+bestaudio', '135+139', 'mp4-480p', 'res:480',
        'hls-312+bestaudio',  # 480p avc1 + best audio
        '788+bestaudio', '780+bestaudio', '397+bestaudio',  # Vertical
        'bestvideo[height=480]+bestaudio/best[height=480]',
    ],
    '720p': [
        '136+bestaudio', '22', '311+bestaudio', 'res:720',
        '298+bestaudio', '232+bestaudio',  # 720@60 avc1 + best audio
        'hls-517+bestaudio', 'hls-637+bestaudio',  # 720p avc1 + best audio
        '398+bestaudio', '247+bestaudio',  # Vertical
        'hls-2890+bestaudio', 'hls-2890',
        'bestvideo[height=720]+bestaudio/best[height=720]',
    ],
    '1080p': [
        '137+bestaudio', '614+bestaudio', 'res:1080',
        '299+bestaudio', '312+bestaudio', '270+bestaudio',  # 1080@60 avc1 + best audio
        'hls-899+bestaudio', 'hls-1271+bestaudio',  # 1080p avc1 + best audio
        '399+bestaudio', '616+bestaudio',  # Vertical
        'hls-4026+bestaudio', 'hls-4026',
        'bestvideo[height=1080]+bestaudio/best[height=1080]',
    ],
    '1440p': [
        '639+bestaudio',  # vp9, best audio, hdr
        '623+bestaudio',  # vp9, best audio, no hdr
        '620+bestaudio', 'res:1440',
        'bestvideo[height=1440]+bestaudio/best[height=1440]',
    ],
    '2160p': [
        '642+bestaudio',  # vp9, best audio, hdr
        '628+bestaudio',  # vp9, best audio, no hdr
        '625+bestaudio', 'res:2160',
        'bestvideo[height=2160]+bestaudio/best[height=2160]',
    ],
    'maximum': ['bestvideo*+bestaudio/best'],
}

# VTT is the only format that a browser can use to display captions on a <video/>.
DEFAULT_CAPTION_FORMAT = 'vtt'
DEFAULT_POSTER_FORMAT = 'jpg'
DEFAULT_CHANNEL_DOWNLOAD_ORDER = 'newest'


def extract_info_key(url: str, ydl: YoutubeDL = YDL, process: bool = False):
    return hashkey(url, process=process)


extract_info_cache = cachetools.TTLCache(maxsize=1_000, ttl=timedelta(minutes=5).total_seconds())


# Cache results for each URL for a few minutes.
@cachetools.cached(cache=extract_info_cache, key=extract_info_key)
def extract_info(url: str, ydl: YoutubeDL = YDL, process: bool = False) -> dict:
    """Get info about a video, channel, or playlist.  Separated for testing."""
    if PYTEST:
        raise RuntimeError(f'Refusing to download {url} during testing! {ydl}')

    return ydl.extract_info(url, download=False, process=process)


def prepare_filename(entry: dict, ydl: YoutubeDL = YDL) -> str:
    """Get filename from YoutubeDL.  Separated for testing."""
    dir_name, file_name = os.path.split(ydl.prepare_filename(entry))
    file_name = escape_file_name(file_name)
    file_name = trim_file_name(file_name)
    return f'{dir_name}/{file_name}'


def preview_filename(filename_format: str) -> str:
    """Return an example video file name formatted using the provided filename format.

    @raise RuntimeError: If the format is invalid.
    """
    if not filename_format.endswith('.%(ext)s'):
        raise RuntimeError('Filename must end with .%(ext)s')

    options = get_videos_downloader_config().yt_dlp_options
    options['outtmpl'] = filename_format
    ydl = YoutubeDL(copy.deepcopy(options))
    entry = dict(
        uploader='WROLPi',
        timestamp=int(now().timestamp()),
        upload_date=now().strftime('%Y%m%d'),
        id='Qz-FuenRylQ',
        title='The title of the video',
        ext='mp4',
        description='A description of the video',
    )
    filename = prepare_filename(entry, ydl=ydl)[1:]

    return filename


@cached_multiprocessing_result
async def fetch_video_duration(url: str) -> int:
    """Get video duration in seconds.  Attempts to get the duration from a Video that has already been downloaded,
    otherwise, fetches the duration using yt-dlp."""
    with get_db_session() as session:
        # Join with Video to get duration; a URL may have other files (such as an Archive).
        video = Video.get_by_url(url, session=session)
        if video and (duration := video.file_group.length):
            logger.debug(f'Using already-known duration {duration} for {url} from FileGroup')
            return duration

    logger.debug(f'Fetching video duration from {url}')
    # Duration can be extracted without processing.
    info = extract_info(url, process=False)
    duration = info['duration']
    logger.info(f'Fetched video duration of {duration} from {url}')
    return duration


class ChannelDownloader(Downloader, ABC):
    """Handles downloading of videos in a Channel or Playlist."""
    name = 'video_channel'
    pretty_name = 'Video Channel'
    listable = False

    def __repr__(self):
        return f'<ChannelDownloader>'

    @staticmethod
    def is_a_playlist(info: dict):
        # A playlist may have an id different from its channel.
        return info['id'] != info.get('channel_id')

    async def do_download(self, download: Download) -> DownloadResult:
        """Update a Channel's catalog, then schedule downloads of every missing video."""
        info = extract_info(download.url, process=False)
        # Resolve the "entries" generator.
        info: dict = resolve_generators(info)
        entries = info.get('entries')
        if entries and isinstance(entries[0], Dict) and entries[0].get('entries'):
            # Entries contains more channels/playlist, tell the Maintainer to specify the URL.
            raise UnrecoverableDownloadError(f'Unable to download {download.url} because the URL is ambiguous.'
                                             f' Try requesting the videos only:'
                                             f' https://example.com -> https://example.com/videos')

        download_settings = download.settings or dict()
        channel_tag_name = i[0] if (i := download_settings.get('channel_tag_name')) else None

        download.sub_downloader = video_downloader.name
        download.info_json = info
        if session := Session.object_session(download):
            # May not have a session during testing.
            session.commit()

        name = info.get('uploader') or info.get('webpage_url_basename')
        if not name:
            raise ValueError(f'Could not find name')
        channel_source_id = info.get('channel_id') or info.get('id')
        channel = get_or_create_channel(channel_source_id, download.url, name, channel_tag_name)
        channel.dict()  # get all attributes while we have the session.

        location = f'/videos/channel/{channel.id}/video' if channel and channel.id else None

        # The settings to send to the VideoDownloader.
        settings = dict()
        if channel:
            settings.update(dict(channel_id=channel.id, channel_url=download.url))
        if download.destination:
            destination = get_absolute_media_path(download.destination)
            settings['destination'] = str(destination)  # Need str for JSON conversion
        if download.tag_names:
            settings['tag_names'] = download.tag_names
        if video_resolutions := download_settings.get('video_resolutions'):
            settings['video_resolutions'] = video_resolutions
        if video_format := download_settings.get('video_format'):
            settings['video_format'] = video_format

        is_a_playlist = self.is_a_playlist(info)
        try:
            if not is_a_playlist:
                await self.prepare_channel_for_downloads(download, channel)
            else:
                logger.debug('Not updating channel because this is a playlist')

            downloads = self.get_missing_videos(download)
            return DownloadResult(
                success=True,
                location=location,
                downloads=downloads,
                settings=settings,
            )
        except Exception as e:
            if PYTEST:
                raise
            kind = 'playlist' if is_a_playlist else 'channel'
            logger.error(f'Failed to update catalog of {kind} {download.url}', exc_info=e)
            return DownloadResult(
                success=False,
                location=location,
                error=str(traceback.format_exc()),
                settings=settings,
            )

    @classmethod
    async def prepare_channel_for_downloads(cls, download: Download, channel: Channel):
        """Update the Channel's video catalog.  Refresh the Channel's files if necessary."""
        logger.debug(f'Preparing {channel} for downloads')
        channel_id = channel.id

        update_channel_catalog(channel, download.info_json)

        with get_db_session() as session:
            channel = get_channel(session, channel_id=channel_id, return_dict=False)
            if not channel.videos or not channel.refreshed:
                logger.warning(f'Refreshing videos in {channel.directory} because {channel} has no video records!')
                await channel.refresh_files(send_events=False)
                session.commit()  # Commit the refresh.
                session.refresh(channel)

    @staticmethod
    def get_missing_videos(download: Download) -> List[str]:
        """
        Return all URLs of Videos in the `info_json` which need to be downloaded.
        """
        downloads = download.info_json['entries']
        total_downloads = len(downloads)

        settings = download.settings or dict()
        title_exclude = settings.get('title_exclude', '')
        title_exclude = [i.lower() for i in title_exclude.split(',') if i]
        title_include = settings.get('title_include', '')
        title_include = [i.lower() for i in title_include.split(',') if i]
        if title_exclude or title_include:
            new_downloads = []
            for i in downloads:
                title = i.get('title', '').lower()
                if title and title_exclude and any(i in title for i in title_exclude):
                    logger.debug(f'Video with title {str(repr(title))} matches {title_exclude=}')
                    continue
                if title and title_include and not any(i in title for i in title_include):
                    logger.debug(f'Video with title {str(repr(title))} matches {title_include=}')
                    continue
                new_downloads.append(i)
            downloads = new_downloads

        # Filter videos by their length.
        try:
            if minimum_duration := settings.get('minimum_duration'):
                downloads = [i for i in downloads if (d := i.get('duration')) and int(d) >= minimum_duration]
            if maximum_duration := settings.get('maximum_duration'):
                downloads = [i for i in downloads if (d := i.get('duration')) and int(d) <= maximum_duration]
        except KeyError as e:
            raise RuntimeError('Unable to filter videos because there is no duration') from e

        # Sort videos now that we have reduced the number necessary to sort, but before we limit count.
        sort_key = settings.get('download_order', DEFAULT_CHANNEL_DOWNLOAD_ORDER)
        # Default is videos are sorted by newest first.
        if sort_key == 'oldest':
            logger.debug(f'Downloading oldest videos from {download.url}')
            downloads = downloads.reverse()
        elif sort_key == 'views':
            # Download videos with most views.
            logger.debug(f'Downloading most viewed videos from {download.url}')
            downloads = sorted(downloads, key=lambda i: i['view_count'], reverse=True)

        # Limit the videos that will be downloads (this allows the user to download the "top 100" videos of a Channel)
        if video_count_limit := settings.get('video_count_limit'):
            logger.debug(f'Limiting video count to {video_count_limit}: {download.url}')
            video_count_limit = int(video_count_limit)
            downloads = downloads[:video_count_limit]

        filtered_entries = len(downloads)
        if filtered_entries != total_downloads:
            logger.info(f'Downloaded channel.  Total downloaded reduced to {filtered_entries} from {total_downloads}')

        # Prefer `webpage_url` before `url` for all entries.
        downloads = [i.get('webpage_url') or i.get('url') for i in downloads]

        # YouTube Shorts are handled specially.
        downloads = [normalize_video_url(i) for i in downloads]

        # Only download those that have not yet been downloaded.
        already_downloaded = [i.url for i in video_downloader.already_downloaded(*downloads)]
        downloads = [i for i in downloads if i not in already_downloaded]

        return downloads


class VideoDownloader(Downloader, ABC):
    """Downloads a single video.

    Store the video in its channel's directory, otherwise store it in `videos/NO CHANNEL`.

    Videos are validated in a few ways.  A video file is valid when it has a complete video stream and an audio stream.
    A complete video stream is validated by taking a screenshot at the end of the video.
    """
    name = 'video'
    pretty_name = 'Videos'

    def __repr__(self):
        return f'<VideoDownloader>'

    @optional_session
    def already_downloaded(self, *urls: str, session: Session = None) -> List:
        # We only consider a video record with a video file as "downloaded".
        file_groups = list(session.query(FileGroup).filter(FileGroup.url.in_(urls), FileGroup.model == 'video'))
        return file_groups

    async def do_download(self, download: Download) -> DownloadResult:
        if download.attempts >= 10:
            raise UnrecoverableDownloadError('Max download attempts reached')

        url = normalize_video_url(download.url)

        # Copy settings into Download (they may be from the ChannelDownloader)
        settings = download.settings or dict()
        download.destination = download.destination or settings.get('destination')
        tag_names = download.tag_names = download.tag_names or settings.get('tag_names')

        # Video may have been downloaded previously, get its location for error reporting.
        with get_db_session() as session:
            video_ = Video.get_by_url(url, session)
            location = video_.location if video_ else None

        try:
            download.info_json = download.info_json or extract_info(url)
        except yt_dlp.utils.DownloadError as e:
            # Video may be private.
            try:
                raise RuntimeError('Failed to extract_info') from e
            except Exception as e:
                return DownloadResult(
                    success=False,
                    location=location,
                    error='\n'.join(traceback.format_exception(e)),
                )

        if not download.info_json:
            raise ValueError(f'Cannot download video with no info_json.')

        channel, channel_directory, channel_id, destination, settings = await self._get_channel(download)

        if destination:
            # Download to the directory specified in the settings.
            out_dir = destination
            logger.debug(f'Downloading {url} to destination {destination} from settings')
        elif channel:
            out_dir = channel_directory
            logger.debug(f'Downloading {url} to channel directory: {channel_directory}')
        else:
            # Download to the default directory if this video has no channel.
            out_dir = get_no_channel_directory()
            logger.debug(f'Downloading {url} to default directory')

        # Make output directory.  (Maybe string from settings)
        out_dir = out_dir if isinstance(out_dir, pathlib.Path) else pathlib.Path(out_dir)
        out_dir = get_absolute_media_path(out_dir)
        out_dir.mkdir(exist_ok=True, parents=True)

        if tag_names and logger.isEnabledFor(logging.DEBUG):
            logger.debug(f'Downloading {url} with {tag_names=}')

        config = get_videos_downloader_config()

        logs = None  # noqa
        try:
            # Use user-provided/channel-provided first, or fallback to defaults from config.
            video_resolutions = settings.get('video_resolutions') or config.video_resolutions
            # yt-dlp expects a string like so: 299+140,298+140,bestvideo*+bestaudio/best
            video_resolutions = ','.join(j for i in video_resolutions for j in VIDEO_RESOLUTION_MAP[i])

            video_format = settings.get('video_format') or config.merge_output_format
            video_path, entry = self.prepare_filename(url, out_dir, video_resolutions, video_format)

            if settings.get('download_metadata_only'):
                # User has requested refresh of video metadata, skip the rest of the video downloader.
                return await self.download_info_json(download, video_path)

            cmd = (
                str(YT_DLP_BIN),
                '-f', video_resolutions,
                '--match-filter', '!is_live',  # Do not attempt to download Live videos.
                '--sub-format', DEFAULT_CAPTION_FORMAT,
                '--convert-subs', DEFAULT_CAPTION_FORMAT,
                '--convert-thumbnails', DEFAULT_POSTER_FORMAT,
                '--merge-output-format', video_format,
                # '--remux-video', video_format,
                '--no-cache-dir',
                '--compat-options', 'no-live-chat',
                # Get top 20 comments, 10 replies per parent.
                '--write-comments',
                '--extractor-args', 'youtube:max_comments=all,20,all,10;comment_sort=top',
                # Use experimental feature to merge files.
                '--ppa', 'Merger+ffmpeg_o1:-strict -2',
            )
            if config.continue_dl:
                cmd = (*cmd, '--continue')
            if config.writesubtitles:
                cmd = (*cmd, '--write-subs', '--write-auto-subs')
            if config.writethumbnail:
                cmd = (*cmd, '--write-thumbnail')
            if config.writeinfojson:
                cmd = (*cmd, '--write-info-json')
            if config.yt_dlp_extra_args:
                cmd = (*cmd, *config.yt_dlp_extra_args.split(' '))
            if config.browser_profile and (
                    (i := settings.get('use_browser_profile')) or (config.always_use_browser_profile and i != False)):
                # Use the browser profile to get cookies, but only if "always_use_browser_profile" is set and
                # "use_browser_profile" is not False, or if "use_browser_profile" is set.
                browser_profile = pathlib.Path(config.browser_profile)
                if browser_profile.exists():
                    browser_profile = browser_profile_to_yt_dlp_arg(browser_profile)
                    cmd = (*cmd, '--cookies-from-browser', browser_profile)
                else:
                    logger.error(f'Browser profile {config.browser_profile} does not exist')

            # Add destination and the video's URL to the command.
            cmd = (*cmd,
                   '-o', video_path,
                   url,
                   )
            # Do the real download.
            result = await self.process_runner(download, cmd, out_dir, debug=True)
            stdout = result.stdout.decode()
            stderr = result.stderr.decode()

            if result.return_code != 0:
                error = f'{stdout}\n\n\n{stderr}\n\nvideo downloader process exited with {result.return_code}'
                return DownloadResult(
                    success=False,
                    error=error,
                    location=location,
                )

            preferred_path = video_path.with_suffix(f'.{video_format}')
            if not video_path.is_file() and preferred_path.is_file():
                # Prepared filename does not exist, but video with preferred video extension does, it was probably
                # remuxed by yt-dlp.
                video_path = preferred_path
                logger.info(f'Using preferred video file which exists: {preferred_path}')

            if video_path.suffix == '.part':
                return DownloadResult(
                    success=False,
                    error=f'Video file that completed was a .part file: {video_path}',
                )

            if not video_path.is_file():
                error = f'{stdout}\n\n\n{stderr}\n\n' \
                        f'Video file could not be found!  {video_path}'
                if '!is_live' in stdout:
                    error = f'{stdout}\n\nVideo was live and did not finish downloading.'
                if ' live event ' in stdout:
                    error = f'{stdout}\n\nVideo will be live and did not finish downloading.'
                return DownloadResult(
                    success=False,
                    error=error,
                    location=location,
                )

            if not ffmpeg_video_complete(video_path):
                return DownloadResult(
                    success=False,
                    error='Video was incomplete',
                    location=location,
                )

            with get_db_session(commit=True) as session:
                # Find any files downloaded with the video (poster, caption, etc.).
                video_paths = glob_shared_stem(video_path)
                # Delete any leftover part files now that we have verified the video is complete.
                video_paths = self._delete_part_files(video_path, video_paths)
                # Rename any special files that do not match the stem.
                video_paths = self.normalize_video_file_names(video_path, video_paths)
                # Create the Video record.
                video = Video.from_paths(session, *video_paths)
                video.source_id = entry['id']
                video.channel_id = channel_id
                video_id, video_info_json_path = video.id, video.info_json_path
                if video_info_json_path and (new_info_json := video.clean_info_json()):
                    video.replace_info_json(new_info_json, clean=False)
                session.commit()

            with get_db_session(commit=True) as session:
                # Second session is started because SQLAlchemy will forget what we have done.
                video = Video.get_by_id(video_id, session)
                if tag_names:
                    existing_names = video.file_group.tag_names
                    for name in tag_names:
                        if name not in existing_names:
                            video.add_tag(name)
                location = video.location

                await video.get_ffprobe_json()

                # Check that video has both audio and video streams.
                if not video.get_streams_by_codec_type('video'):
                    return DownloadResult(
                        success=False,
                        error='Video was downloaded but did not contain video stream',
                        location=location,
                    )
                if not video.get_streams_by_codec_type('audio'):
                    return DownloadResult(
                        success=False,
                        error='Video was downloaded but did not contain audio stream',
                        location=location,
                    )
                logger.info(f'Successfully downloaded video {url} {video}')

            with get_db_session(commit=True) as session:
                await Video.delete_duplicate_videos(session, download.url, entry['id'], video_path)

        except UnrecoverableDownloadError:
            raise
        except yt_dlp.utils.UnsupportedError as e:
            raise UnrecoverableDownloadError('URL is not supported by yt-dlp') from e
        except Exception as e:
            logger.warning(f'VideoDownloader failed to download: {url}', exc_info=e)
            if _skip_download(e):
                # The video failed to download, and the error will never be fixed.  Skip it forever.
                try:
                    source_id = download.info_json.get('id')
                    logger.warning(f'Adding video "{source_id}" to skip list for this channel.  WROLPi will not '
                                   f'attempt to download it again.')
                    download.add_to_skip_list()
                except Exception:
                    # Could not skip this video, it may not have a channel.
                    logger.warning(f'Could not skip video {url}')

                # Skipped downloads should not be tried again.
                raise UnrecoverableDownloadError() from e
            # Download did not succeed, try again later.
            if logs and (stderr := logs.get('stderr')):
                error = f'{stderr}\n\n{traceback.format_exc()}'
            else:
                error = str(traceback.format_exc())
            return DownloadResult(success=False, error=error, location=location)

        logger.debug(f'Downloaded video {location=}')

        result = DownloadResult(
            success=True,
            location=location,
        )
        return result

    @staticmethod
    async def _get_channel(download: Download) \
            -> Tuple[Optional[Channel], Optional[pathlib.Path], Optional[int], Optional[pathlib.Path], dict]:
        settings = download.settings or dict()
        channel_tag_name = i[0] if (i := settings.get('channel_tag_name')) else None

        found_channel = None
        # Look for Channel using channel data first, fallback to uploader data.
        channel_name = download.info_json.get('channel') or download.info_json.get('uploader')
        channel_source_id = download.info_json.get('channel_id') or download.info_json.get('uploader_id')
        channel_url = download.info_json.get('channel_url') or download.info_json.get('uploader_url')
        channel = None
        if channel_name or channel_source_id or channel_url:
            # Try to find the channel via info_json from yt-dlp.
            try:
                channel = get_or_create_channel(source_id=channel_source_id, url=channel_url, name=channel_name,
                                                tag_name=channel_tag_name)
                if channel:
                    found_channel = 'yt_dlp'
                    logger.debug(f'Found a channel with source_id {channel=}')
            except UnknownChannel:
                # Can't find a channel, use the no channel directory.
                pass
        destination = download.destination
        if not channel and destination:
            # Destination may find Channel if not already found.
            try:
                channel = get_channel(directory=destination, return_dict=False)
                found_channel = 'download_settings_directory'
                logger.debug(f'Found a channel that shares the destination directory {channel=}')
            except UnknownChannel:
                # Destination must not be a channel.
                pass
        channel_id = download.channel_id
        channel_url = settings.get('channel_url')
        if not channel and (channel_id or channel_url):
            # Could not find Channel via yt-dlp info_json, use info from ChannelDownloader if it created this Download.
            logger.info(f'Using download.settings to find channel')
            try:
                channel = get_channel(channel_id=channel_id, url=channel_url, return_dict=False)
                logger.debug(f'Found channel with channel url {channel=}')
            except UnknownChannel:
                # We do not need a Channel if we have a destination directory.
                if not destination:
                    raise
            if channel:
                found_channel = 'download_settings'

        channel_id = channel.id if channel else None
        channel_directory = channel.directory if channel else None
        if found_channel == 'yt_dlp':
            logger.debug(f'Found {channel} using yt_dlp')
        elif found_channel == 'download_settings':
            logger.info(f'Found {channel} using Download.settings')
        elif found_channel == 'download_settings_directory':
            logger.info(f'Found {channel} using Download.settings directory')
        else:
            logger.warning('Could not find channel')

        return channel, channel_directory, channel_id, destination, settings

    @staticmethod
    def prepare_filename(url: str, out_dir: pathlib.Path, video_resolutions: str, video_format: str) \
            -> Tuple[pathlib.Path, dict]:
        """Get the full path of a video file from its URL using yt-dlp."""
        if not out_dir.is_dir():
            raise ValueError(f'Output directory does not exist! {out_dir=}')

        # YoutubeDL expects specific options, add onto the default options
        config = get_videos_downloader_config()
        options = config.yt_dlp_options
        # yt-dlp expects the absolute path.
        options['outtmpl'] = f'{out_dir}/{config.file_name_format}'
        options['merge_output_format'] = video_format
        # options['remuxvideo'] = video_format
        options['format'] = video_resolutions
        options['cachdir'] = YTDLP_CACHE_DIR

        # Create a new YoutubeDL for the output directory.
        ydl = YoutubeDL(copy.deepcopy(options))
        ydl.params['logger'] = ydl_logger
        ydl.add_default_info_extractors()

        # Get the path where the video will be saved.
        try:
            entry = extract_info(url, ydl=ydl, process=True)
            final_filename = pathlib.Path(prepare_filename(entry, ydl=ydl)).absolute()
        except DownloadError as e:
            if ' Cannot write ' in str(e):
                # yt-dlp does not handle long file names well, get the name from the error (lol)
                last_line = str(e).splitlines()[-1]
                full_path = last_line.split(' file ')[-1].strip()
                if not full_path.startswith('/'):
                    logger.error(f'Failed to extract filename from {last_line}')
                    raise
            else:
                raise

            # Split filename from parent.
            full_path = pathlib.Path(full_path)
            parent = full_path.parent
            filename, _ = split_path_stem_and_suffix(full_path.name)

            # Trim long filename, add video suffix, add back into parent directory.
            filename = escape_file_name(filename)
            final_filename = parent / f'{filename}.{video_format}'
            final_filename = trim_file_name(final_filename)
            logger.debug(f'Video file name was too long.  Trimmed to: {final_filename.name}')

            # Get entry info json.
            options['outtmpl'] = str(final_filename)
            ydl = YoutubeDL(copy.deepcopy(options))
            ydl.params['logger'] = ydl_logger
            ydl.add_default_info_extractors()
            entry = extract_info(url, ydl=ydl, process=True)

        logger.debug(f'Downloading {url} to {repr(str(final_filename))}')
        return final_filename, entry

    @staticmethod
    async def download_info_json(download: Download, video_path: pathlib.Path) -> DownloadResult:
        """User has requested to refresh Video metadata.  Download only metadata files to temporary directory.
        Replace existing metadata files only after successful download."""
        url = download.url
        source_id = download.info_json['id']

        with get_db_session() as session:
            # Delete any duplicate videos before attempting to get info json.
            deleted = await Video.delete_duplicate_videos(session, download.url, source_id, video_path)
            if deleted:
                session.commit()

        with get_db_session() as session:
            # Find the existing video, replace its info json.
            video = Video.get_by_url(url, session)

            location = f'/videos/video/{video.id}'
            if video.channel_id:
                location = f'/videos/channel/{video.channel_id}/video/{video.id}'

        # Download video info json directly using yt-dlp.
        try:
            info_json = download_video_info_json(url)
        except Exception as e:
            logger.error('Failed to download video info json', exc_info=e)
            return DownloadResult(success=False, error='Failed to download video info json')

        with get_db_session(commit=True) as session:
            # Find the existing video, replace its info json.
            video = Video.get_by_url(url, session)
            video.replace_info_json(info_json)

            if video.get_comments():
                video.have_comments = True

            await video.get_ffprobe_json()

        logger.debug(f'Downloaded video info json {location=}')
        logger.info(f'Successfully downloaded video info json {url} {video}')

        return DownloadResult(success=True, location=location)

    @staticmethod
    def _delete_part_files(video_file: pathlib.Path, files: list[pathlib.Path]) -> list[pathlib.Path]:
        """Delete temporary "part" files that are used by yt-dlp when downloading video (and related) files."""
        files = list(files)

        video_suffix = video_file.suffix.lstrip('.')

        # Delete any files in this group that end with .part.
        for part_file in [i for i in files if i.name.endswith('.part')]:
            logger.warning(f'Deleting leftover .part file: {part_file}')
            part_file.unlink()
            files.remove(part_file)

        # Delete any video files that are a temporary file that contain the "format" number.
        # Example:  The Video Title.f616.mp4
        video_files = [i for i in files if i != video_file and i.name.endswith(video_suffix)]
        for part_video in video_files:
            if VIDEO_FORMAT_PARSER.match(part_video.stem):
                # Extra yt-dlp format video file that is not the video file, delete it.
                logger.warning(f'Deleting leftover incomplete video file: {part_video}')
                part_video.unlink()
                files.remove(part_video)

        return files

    @staticmethod
    def normalize_video_file_names(video_path: pathlib.Path, files: List[pathlib.Path]) -> List[pathlib.Path]:
        """Video files can have unpredictable names, rename any video files as necessary to make them share the same
        stem."""
        video_stem, _ = split_path_stem_and_suffix(video_path.name)
        new_files = []
        for file in files:
            suffix = file.name[len(video_stem):]
            if suffix.endswith('.vtt'):
                _, normal_suffix = split_path_stem_and_suffix(file.name)
                if suffix != normal_suffix:
                    # Video captions file has extra characters in the suffix from yt-dlp.
                    # Example:  .en-uYU-mmqFLq8.vtt -> .en.vtt
                    lang, _, suffix = VTT_SUFFIX_PARSER.match(suffix.strip()).groups()
                    suffix = f'.{lang}.{suffix}'
                    file = file.rename(video_path.with_suffix(suffix))
            new_files.append(file)

        return new_files


VTT_SUFFIX_PARSER = re.compile(r'^\.([a-z]{2,3})-(.+?)\.(vtt|srt)$', re.IGNORECASE)

VIDEO_FORMAT_PARSER = re.compile(r'^.+?\.f\d{2,4}')

channel_downloader = ChannelDownloader()
# Videos may match the ChannelDownloader, give it a higher priority.
video_downloader = VideoDownloader()


def get_or_create_channel(source_id: str = None, url: str = None, name: str = None, tag_name: str = None) -> Channel:
    """
    Attempt to find a Channel using the provided params.  The params are in order of reliability.

    Creates a new Channel if one cannot be found.
    """
    try:
        channel = get_channel(source_id=source_id, url=url, name=name, return_dict=False)
        # Get all properties while we have the session.
        channel.dict()
        return channel
    except UnknownChannel:
        pass

    if not name:
        raise UnknownChannel(f'Cannot create channel without a name')

    # Channel does not exist.  Create one in the video directory.
    channel_directory = format_videos_destination(name, tag_name, url)
    if not channel_directory.is_dir():
        channel_directory.mkdir(parents=True)
    data = ChannelPostRequest(
        source_id=source_id,
        name=name,
        url=url,
        directory=str(channel_directory.relative_to(get_media_directory())),
        tag_name=tag_name,
    )
    channel = create_channel(data=data, return_dict=False)
    # Create the directory now that the channel is approved.
    channel_directory.mkdir(exist_ok=True)
    # Get all properties while we have the session.
    channel.dict()

    return channel


def update_channel_catalog(channel: Channel, info: dict):
    """
    Connect to the Channel's host website and pull a catalog of all videos.  Insert any new videos into the DB.

    It is expected that any missing videos will be downloaded later.
    """
    logger.info(f'Downloading video list for {channel} at {channel.url}')

    # Resolve all entries to dictionaries.
    entries = info['entries'] = list(info['entries'])

    # yt-dlp may hand back a list of URLs, lets use the "Uploads" URL, if available.
    try:
        entries[0]['id']
    except Exception:
        logger.warning('yt-dlp did not return a list of URLs')
        for entry in entries:
            if entry['title'] == 'Uploads':
                logger.info('Youtube-DL gave back a list of URLs, found the "Uploads" URL and using it.')
                info = extract_info(entry['url'])
                break

    with get_db_session(commit=True) as session:
        # Get the channel in this new context.
        channel: Channel = session.query(Channel).filter_by(id=channel.id).one()

        channel.info_json = info
        channel.info_date = now()
        channel.source_id = info.get('id')
        channel_id = channel.id

    # Write the Channel's info to a JSON file.
    if channel.directory:
        info_json_path = channel.info_json_path
        with info_json_path.open('wt') as fh:
            json.dump(info, fh, indent=2, sort_keys=True)
        logger.debug(f'Wrote channel info json to {info_json_path}')
    else:
        logger.debug(f'Skipping channel info json because it does not have a directory: {channel}')

    logger.info(f'Finished downloading video list for {channel} found {len(entries)} videos')

    # Update all view counts using the latest from the Channel's info_json.
    background_task(update_view_counts_and_censored(channel_id))


UNRECOVERABLE_ERRORS = {
    '404: Not Found',
    'requires payment',
    'Content Warning',
    'Did not get any data blocks',
    'Sign in',
    'This live stream recording is not available.',
    'members-only content',
    "You've asked yt-dlp to download the URL",
}


def _skip_download(error):
    """Return True if the error is unrecoverable and the video should be skipped in the future."""
    error_str = str(error)
    for msg in UNRECOVERABLE_ERRORS:
        if msg in error_str:
            return True
    return False
