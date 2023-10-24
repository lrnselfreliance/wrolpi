#! /usr/bin/env python3
import json
import pathlib
import re
import traceback
from abc import ABC
from typing import Tuple, List, Dict

import yt_dlp.utils
from sqlalchemy.orm import Session
from yt_dlp import YoutubeDL
from yt_dlp.extractor import YoutubeTabIE  # noqa

from wrolpi.cmd import YT_DLP_BIN
from wrolpi.common import logger, get_media_directory, escape_file_name, resolve_generators, background_task, \
    format_json_file
from wrolpi.dates import now
from wrolpi.db import get_db_session
from wrolpi.db import optional_session
from wrolpi.downloader import Downloader, Download, DownloadResult
from wrolpi.errors import UnrecoverableDownloadError
from wrolpi.files.lib import glob_shared_stem
from wrolpi.files.models import FileGroup
from wrolpi.vars import PYTEST
from .channel.lib import create_channel, get_channel
from .common import get_no_channel_directory, get_videos_directory, update_view_counts, ffmpeg_video_complete
from .errors import UnknownChannel
from .lib import get_downloader_config
from .models import Video, Channel
from .schema import ChannelPostRequest
from .video_url_resolver import normalize_youtube_shorts_url

logger = logger.getChild(__name__)
ydl_logger = logger.getChild('youtube-dl')

YDL = YoutubeDL()
YDL.params['logger'] = ydl_logger
YDL.add_default_info_extractors()

# Channels are handled differently than a single video.
ChannelIEs = {
    YoutubeTabIE,
}

PREFERRED_VIDEO_EXTENSION = 'mp4'
PREFERRED_VIDEO_FORMAT = ','.join([
    'res:720',  # Use the best 720p available first
    '136+140',  # 130=720p video-only, 140= high quality audio only
    '22',  # 720p video with audio
    'mp4-480p',
    'bestvideo*+bestaudio/best',  # Download the highest resolution as a last resort (can be quite large).
])
PREFERRED_CAPTION_FORMAT = 'vtt'
PREFERRED_POSTER_FORMAT = 'jpg'


def extract_info(url: str, ydl: YoutubeDL = YDL, process=False) -> dict:
    """Get info about a video.  Separated for testing."""
    return ydl.extract_info(url, download=False, process=process)


def prepare_filename(entry: dict, ydl: YoutubeDL = YDL) -> str:
    """Get filename from YoutubeDL.  Separated for testing."""
    return ydl.prepare_filename(entry)


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
        logger.debug(f'is_a_playlist {info["id"]=} {info.get("channel_id")=}')
        return info['id'] != info.get('channel_id')

    async def do_download(self, download: Download) -> DownloadResult:
        """Update a Channel's catalog, then schedule downloads of every missing video."""
        info = extract_info(download.url, process=False)
        # Resolve the "entries" generator.
        info: Dict = resolve_generators(info)
        entries = info.get('entries')
        if entries and isinstance(entries[0], Dict) and entries[0].get('entries'):
            # Entries contains more channels/playlist, tell the Maintainer to specify the URL.
            raise UnrecoverableDownloadError(f'Unable to download {download.url} because the URL is ambiguous.'
                                             f' Try requesting the videos only:'
                                             f' https://example.com -> https://example.com/videos')

        download.sub_downloader = video_downloader.name
        download.info_json = info
        if session := Session.object_session(download):
            # May not have a session during testing.
            session.commit()

        name = info.get('uploader') or info.get('webpage_url_basename')
        if not name:
            raise ValueError(f'Could not find name')
        channel_source_id = info.get('channel_id') or info.get('id')
        channel = get_or_create_channel(channel_source_id, download.url, name)
        channel.dict()  # get all attributes while we have the session.

        location = f'/videos/channel/{channel.id}/video' if channel and channel.id else None

        # The settings to send to the VideoDownloader.
        settings = dict()
        if channel:
            settings.update(dict(channel_id=channel.id, channel_url=download.url))
        # Downloads will inherit the destination, if defined.
        destination = download.settings.get('destination') if download.settings else None
        if destination:
            settings['destination'] = destination

        is_a_playlist = self.is_a_playlist(info)
        try:
            if not is_a_playlist:
                await self.prepare_channel_for_downloads(download, channel)
            else:
                logger.debug('Not updating channel because this is a playlist')

            downloads = self.get_missing_videos(download, channel)
            return DownloadResult(
                success=True,
                location=location,
                downloads=downloads,
                settings=settings,
            )
        except Exception:
            if PYTEST:
                raise
            kind = 'playlist' if is_a_playlist else 'channel'
            logger.warning(f'Failed to update catalog of {kind} {download.url}')
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
    def get_missing_videos(download: Download, channel: Channel) -> List[str]:
        """
        Return all URLs of Videos in the `info_json` which need to be downloaded.
        """
        downloads = download.info_json['entries']
        if channel.match_regex:
            # Only download Videos that have matching titles.
            match_regex = re.compile(channel.match_regex)
            downloads = [i for i in downloads if (title := i.get('title')) and match_regex.match(title)]

        # Prefer `webpage_url` before `url` for all entries.
        downloads = [i.get('webpage_url') or i.get('url') for i in downloads]

        # YouTube Shorts are handled specially.
        downloads = [normalize_youtube_shorts_url(i) for i in downloads]

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

        url = download.url
        info = download.info_json or extract_info(url)

        if not info:
            raise ValueError(f'Cannot download video with no info_json.')

        found_channel = None

        channel_name = info.get('channel')
        source_channel_id = info.get('channel_id')
        channel_url = info.get('channel_url')
        channel = None
        if channel_name or source_channel_id:
            # Try to find the channel via info_json from yt-dlp.
            try:
                channel = get_or_create_channel(source_id=source_channel_id, url=channel_url, name=channel_name)
                if channel:
                    found_channel = 'yt_dlp'
            except UnknownChannel:
                # Can't find a channel, use the no channel directory.
                pass

        settings = download.settings or dict()
        destination = settings.get('destination')
        if not channel and destination:
            # Destination may override the real Channel.
            try:
                channel = get_channel(directory=destination, return_dict=False)
                found_channel = 'download_settings_directory'
            except UnknownChannel:
                # Destination must not be a channel.
                pass

        local_channel_id = settings.get('channel_id')
        channel_url = settings.get('channel_url')
        if not channel and (local_channel_id or channel_url):
            # Could not find channel via yt-dlp info_json, use info from ChannelDownloader if it created this Download.
            logger.info(f'Using download.settings to find channel')
            try:
                channel = get_channel(channel_id=local_channel_id, url=channel_url, return_dict=False)
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

        if destination:
            # Download to the directory specified in the settings.
            out_dir = pathlib.Path(settings['destination'])
            logger.debug(f'Downloading {url} to destination from settings')
        elif channel:
            out_dir = channel_directory
            logger.debug(f'Downloading {url} to channel directory')
        else:
            # Download to the default directory if this video has no channel.
            out_dir = get_no_channel_directory()
            logger.debug(f'Downloading {url} to default directory')
        out_dir.mkdir(exist_ok=True, parents=True)

        logs = None  # noqa
        try:
            video_path, entry = self.prepare_filename(url, out_dir)
            # Do the real download.
            file_name_format = '%(uploader)s_%(upload_date)s_%(id)s_%(title)s.%(ext)s'
            cmd = (
                str(YT_DLP_BIN),
                '-cw',  # Continue downloads, do not clobber existing files.
                '-f', PREFERRED_VIDEO_FORMAT,
                '--match-filter', '!is_live',  # Do not attempt to download Live videos.
                '--write-subs',
                '--write-auto-subs',
                '--sub-format', PREFERRED_CAPTION_FORMAT,
                '--convert-subs', PREFERRED_CAPTION_FORMAT,
                '--convert-thumbnails', PREFERRED_POSTER_FORMAT,
                '--write-thumbnail',
                '--write-info-json',
                '--merge-output-format', PREFERRED_VIDEO_EXTENSION,
                '--remux-video', PREFERRED_VIDEO_EXTENSION,
                '-o', file_name_format,
                '--no-cache-dir',
                '--compat-options', 'no-live-chat',
                # Use experimental feature to merge files.
                '--ppa', 'Merger+ffmpeg_o1:-strict -2',
                url,
            )
            return_code, logs, _ = await self.process_runner(url, cmd, out_dir)

            stdout = logs['stdout'].decode() if hasattr(logs['stdout'], 'decode') else logs['stdout']
            stderr = logs['stderr'].decode() if hasattr(logs['stderr'], 'decode') else logs['stderr']

            if return_code != 0:
                error = f'{stdout}\n\n\n{stderr}\n\nvideo downloader process exited with {return_code}'
                return DownloadResult(
                    success=False,
                    error=error,
                )

            preferred_path = video_path.with_suffix(f'.{PREFERRED_VIDEO_EXTENSION}')
            if not video_path.is_file() and preferred_path.is_file():
                # Prepared filename does not exist, but video with preferred video extension does, it was probably
                # remuxed by yt-dlp.
                video_path = preferred_path
                logger.info(f'Using preferred video file which exists: {preferred_path}')

            if not video_path.is_file():
                error = f'{stdout}\n\n\n{stderr}\n\n' \
                        f'Video file could not be found!  {video_path}'
                return DownloadResult(
                    success=False,
                    error=error,
                )

            if not ffmpeg_video_complete(video_path):
                return DownloadResult(
                    success=False,
                    error='Video was incomplete',
                )

            with get_db_session(commit=True) as session:
                # Find any files downloaded with the video (poster, caption, etc.).
                video_paths = glob_shared_stem(video_path)
                video = Video.from_paths(session, *video_paths)
                video.source_id = entry['id']
                video.channel_id = channel_id
                video_id = video.id

                if video.info_json_path:
                    format_json_file(video.info_json_path)

                session.commit()

                if download.settings and (tag_names := download.settings.get('tag_names')):
                    existing_names = video.file_group.tag_names
                    for name in tag_names:
                        if name not in existing_names:
                            video.add_tag(name)

                # Check that video has both audio and video streams.
                await video.get_ffprobe_json()
                if not video.get_streams_by_codec_type('video'):
                    return DownloadResult(
                        success=False,
                        error='Video was downloaded but did not contain video stream',
                    )
                if not video.get_streams_by_codec_type('audio'):
                    return DownloadResult(
                        success=False,
                        error='Video was downloaded but did not contain audio stream',
                    )
                session.commit()

        except UnrecoverableDownloadError:
            raise
        except yt_dlp.utils.UnsupportedError as e:
            raise UnrecoverableDownloadError('URL is not supported by yt-dlp') from e
        except Exception as e:
            logger.warning(f'VideoDownloader failed to download: {download.url}', exc_info=e)
            if _skip_download(e):
                # The video failed to download, and the error will never be fixed.  Skip it forever.
                try:
                    source_id = info.get('id')
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
            return DownloadResult(success=False, error=error)

        if channel_id:
            location = f'/videos/channel/{channel_id}/video/{video_id}'
        else:
            location = f'/videos/video/{video_id}'
        result = DownloadResult(
            success=True,
            location=location,
        )
        return result

    @staticmethod
    def prepare_filename(url: str, out_dir: pathlib.Path) -> Tuple[pathlib.Path, dict]:
        """Get the full path of a video file from its URL."""
        if not out_dir.is_dir():
            raise ValueError(f'Output directory does not exist! {out_dir=}')

        # YoutubeDL expects specific options, add onto the default options
        options = get_downloader_config().dict()
        options['outtmpl'] = f'{out_dir}/{options["file_name_format"]}'
        options['merge_output_format'] = PREFERRED_VIDEO_EXTENSION
        options['remuxvideo'] = PREFERRED_VIDEO_EXTENSION
        options['format'] = PREFERRED_VIDEO_FORMAT

        # Create a new YoutubeDL for the output directory.
        ydl = YoutubeDL(options)
        ydl.params['logger'] = ydl_logger
        ydl.add_default_info_extractors()

        # Get the path where the video will be saved.
        entry = extract_info(url, ydl=ydl, process=True)
        final_filename = pathlib.Path(prepare_filename(entry, ydl=ydl)).absolute()

        logger.debug(f'Downloading {url} to {out_dir}')
        return final_filename, entry


channel_downloader = ChannelDownloader()
# Videos may match the ChannelDownloader, give it a higher priority.
video_downloader = VideoDownloader()


def get_or_create_channel(source_id: str = None, url: str = None, name: str = None) -> Channel:
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
    channel_directory = get_videos_directory() / escape_file_name(name)
    if not channel_directory.is_dir():
        channel_directory.mkdir(parents=True)
    data = ChannelPostRequest(
        source_id=source_id,
        name=name,
        url=url,
        directory=str(channel_directory.relative_to(get_media_directory())),
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
        info_json_path = channel.directory / f'{channel.name}.info.json'
        with info_json_path.open('wt') as fh:
            json.dump(info, fh, indent=2)
        logger.debug(f'Wrote channel info json to {info_json_path}')
    else:
        logger.debug(f'Skipping channel info json because it does not have a directory: {channel}')

    logger.info(f'Finished downloading video list for {channel} found {len(entries)} videos')

    # Update all view counts using the latest from the Channel's info_json.
    background_task(update_view_counts(channel_id))


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
