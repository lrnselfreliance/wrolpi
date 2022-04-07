#! /usr/bin/env python3
import json
import pathlib
import re
from abc import ABC
from typing import Tuple, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import NoResultFound
from yt_dlp import YoutubeDL
from yt_dlp.extractor import YoutubeTabIE
from yt_dlp.utils import UnsupportedError, DownloadError

from wrolpi.cmd import which
from wrolpi.common import logger, sanitize_link, extract_domain
from wrolpi.dates import now
from wrolpi.db import get_db_session, get_db_curs
from wrolpi.downloader import Downloader, Download, DOWNLOAD_MANAGER_CONFIG
from wrolpi.errors import UnknownChannel, ChannelURLEmpty, UnrecoverableDownloadError
from wrolpi.vars import PYTEST
from .channel.lib import create_channel, get_channel
from .common import apply_info_json, get_channel_source_id, get_no_channel_directory, \
    get_videos_directory
from .lib import upsert_video, refresh_channel_videos, get_downloader_config
from .models import Video, Channel
from .video_url_resolver import video_url_resolver

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
PREFERRED_VIDEO_FORMAT = 'best[height=720],22,720p,mp4-480p,mp4-360p,mp4-240p,18,bestvideo+bestaudio'


class ChannelDownloader(Downloader, ABC):
    """
    Handling downloading of all Videos in a Channel.
    """
    name = 'video_channel'
    pretty_name = 'Video Channel'
    listable = False

    def __repr__(self):
        return f'<ChannelDownloader name={self.name}>'

    @classmethod
    def valid_url(cls, url) -> Tuple[bool, None]:
        for ie in ChannelIEs:
            if ie.suitable(url):
                return True, None
        logger.debug(f'{cls.__name__} not suitable for {url}')
        return False, None

    def do_download(self, download: Download):
        """
        Update a Channel's catalog, then schedule downloads of every missing video.
        """
        with get_db_session() as session:
            channel = session.query(Channel).filter_by(url=download.url).one_or_none()

            if not channel:
                # Couldn't get channel by URL, this is probably a playlist.  Find the channel for the playlist.
                channel_source_id = get_channel_source_id(download.url)
                channel = get_channel(channel_source_id, return_dict=False)

        update_channel(channel)

        domain = extract_domain(download.url)
        missing_videos = find_all_missing_videos(channel.link)
        with get_db_session(commit=True) as session:
            for video_id, source_id, missing_video in missing_videos:
                url = video_url_resolver(domain, missing_video)
                if url in DOWNLOAD_MANAGER_CONFIG.skip_urls:
                    # Don't try to download skipped videos.
                    continue
                # Schedule any missing videos for download.
                download = self.manager.get_or_create_download(url, session)
                download.downloader = 'video'

        if PYTEST:
            self.manager.do_downloads_sync()
        else:
            self.manager.start_downloads()

        return True


YT_DLP_BIN = which(
    'yt-dlp',
    '/usr/local/bin/yt-dlp',  # Location in docker container
    '/opt/wrolpi/venv/bin/yt-dlp',  # Use virtual environment location
    warn=True,
)


class VideoDownloader(Downloader, ABC):
    """
    Download a single video.  Store the video in its channel's directory, otherwise store it in `videos/NO CHANNEL`.
    """
    name = 'video'
    pretty_name = 'Videos'

    def __repr__(self):
        return f'<VideoDownloader name={self.name}>'

    @classmethod
    def valid_url(cls, url) -> Tuple[bool, Optional[dict]]:
        """
        Match against all Youtube-DL Info Extractors, except those that match a Channel.
        """
        for ie in YDL._ies.values():
            if ie.suitable(url) and not ChannelDownloader.valid_url(url)[0]:
                try:
                    info = YDL.extract_info(url, download=False, process=False)
                    return True, info
                except UnsupportedError:
                    logger.debug(f'Video downloader extract_info failed for {url}')
                    return False, None
                except DownloadError:
                    logger.debug(f'Video downloader extract_info failed for {url}')
                    return False, None
        logger.debug(f'{cls.__name__} not suitable for {url}')
        return False, None

    def do_download(self, download: Download):
        if download.attempts >= 10:
            raise UnrecoverableDownloadError('Max download attempts reached')

        url = download.url
        info = download.info_json

        if not info:
            # Info was not fetched by the DownloadManager, lets get it.
            valid, info = self.valid_url(url)
            if not valid:
                raise UnrecoverableDownloadError(f'{self} cannot download {url}')
            session = Session.object_session(download)
            download.info_json = info
            session.commit()

        channel_name = info.get('channel')
        channel_id = info.get('channel_id')
        channel = None
        if channel_name or channel_id:
            channel_url = info.get('channel_url')
            channel = get_or_create_channel(channel_id, None, channel_url, channel_name)

        # Use the default directory if this video has no channel.
        out_dir = get_no_channel_directory()
        if channel:
            out_dir = channel.directory.path
        out_dir.mkdir(exist_ok=True, parents=True)

        try:
            video_path, entry = self.prepare_filename(url, out_dir)
            # Do the real download.
            file_name_format = '%(uploader)s_%(upload_date)s_%(id)s_%(title)s.%(ext)s'
            cmd = [
                str(YT_DLP_BIN),
                '-cw',  # Continue downloads, do not clobber existing files.
                '-f', PREFERRED_VIDEO_FORMAT,
                '--match-filter', '!is_live',  # Do not attempt to download Live videos.
                '--write-subs',
                '--write-auto-subs',
                '--write-thumbnail',
                '--write-info-json',
                '--merge-output-format', PREFERRED_VIDEO_EXTENSION,
                '-o', file_name_format,
                url,
            ]
            return_code = self.process_runner(url, cmd, out_dir)

            if return_code != 0:
                raise ValueError(f'video downloader process exited with {return_code}')

            if not video_path.is_file():
                raise ValueError(f'Video file could not be found!  {video_path}')
        except UnrecoverableDownloadError:
            raise
        except Exception as e:
            logger.warning(f'VideoDownloader failed to download: {download.url}', exc_info=e)
            if _skip_download(e):
                # The video failed to download, and the error will never be fixed.  Skip it forever.
                try:
                    source_id = info.get('id')
                    logger.warning(f'Adding video "{source_id}" to skip list for this channel.  WROLPi will not '
                                   f'attempt to download it again.')

                    with get_db_session(commit=True) as session:
                        channel = session.query(Channel).filter_by(id=channel.id).one()
                        channel.add_video_to_skip_list(source_id)
                except Exception:
                    # Could not skip this video, it may not have a channel.
                    logger.warning(f'Could not skip video {url}')

                # Skipped downloads should not be tried again.
                raise UnrecoverableDownloadError() from e
            return

        with get_db_session(commit=True) as session:
            # If the video is from a channel, it will already be in the database.
            source_id = entry['id']
            existing_video = session.query(Video).filter_by(source_id=source_id).one_or_none()
            id_ = existing_video.id if existing_video else None

            upsert_video(session, video_path, channel, id_=id_)

        # Successful download.
        return True

    @staticmethod
    def prepare_filename(url: str, out_dir: pathlib.Path) -> Tuple[pathlib.Path, dict]:
        if not out_dir.is_dir():
            raise ValueError(f'Output directory does not exist! {out_dir=}')

        # YoutubeDL expects specific options, add onto the default options
        options = get_downloader_config().dict()
        options['outtmpl'] = f'{out_dir}/{options["file_name_format"]}'
        options['merge_output_format'] = PREFERRED_VIDEO_EXTENSION

        logger.debug(f'Downloading {url} to {out_dir}')

        # Create a new YoutubeDL for the output directory.
        ydl = YoutubeDL(options)
        ydl.params['logger'] = ydl_logger
        ydl.add_default_info_extractors()

        # Perform the real download.  This saves multiple files.
        entry = ydl.extract_info(url, download=False, process=True)
        final_filename = pathlib.Path(ydl.prepare_filename(entry))
        return final_filename, entry


channel_downloader = ChannelDownloader()
# Videos may match the ChannelDownloader, give it a higher priority.
video_downloader = VideoDownloader(40)


def get_or_create_channel(source_id: str = None, link: str = None, url: str = None, name: str = None) -> Channel:
    """
    Attempt to find a Channel using the provided params.  The params are in order of reliability.

    Creates a new Channel if one cannot be found.
    """
    if not link and name:
        link = sanitize_link(name)

    try:
        channel = get_channel(link=link, source_id=source_id, url=url, return_dict=False)
        return channel
    except UnknownChannel:
        pass

    # Channel does not exist.  Create one in the video directory.
    channel_directory = get_videos_directory() / name
    if not channel_directory.is_dir():
        channel_directory.mkdir(parents=True)
    data = dict(
        name=name,
        url=url,
        link=link,
        domain=extract_domain(url),
        directory=str(channel_directory),
        source_id=source_id,
    )
    channel = create_channel(data, return_dict=False)
    # Create the directory now that the channel is approved.
    channel_directory.mkdir(exist_ok=True)

    return channel


def update_channel(channel: Channel):
    """
    Connect to the Channel's host website and pull a catalog of all videos.  Insert any new videos into the DB.

    It is expected that any missing videos will be downloaded later.
    """
    logger.info(f'Downloading video list for {channel.name} at {channel.url}  This may take several minutes.')
    info = YDL.extract_info(channel.url, download=False, process=False)
    if 'url' in info:
        url = info['url']
        info = YDL.extract_info(url, download=False, process=False)

    # Resolve all entries to dictionaries.
    entries = info['entries'] = list(info['entries'])

    # yt-dlp may hand back a list of URLs, lets use the "Uploads" URL, if available.
    try:
        entries[0]['id']
    except Exception:
        for entry in entries:
            if entry['title'] == 'Uploads':
                logger.info('Youtube-DL gave back a list of URLs, found the "Uploads" URL and using it.')
                info = YDL.extract_info(entry['url'], download=False, process=False)
                entries = info['entries'] = list(info['entries'])
                break

    # This is all the source id's that are currently available.
    try:
        all_source_ids = {i['id'] for i in entries}
    except KeyError as e:
        logger.warning(f'No ids for entries!  Was the channel update successful?  Is the channel URL correct?')
        logger.warning(f'entries: {entries}')
        raise KeyError('No id key for entry!') from e

    # In order to store the Video's URL, we will need a quick lookup.
    urls = {i['id']: i.get('webpage_url') for i in entries}

    with get_db_session(commit=True) as session:
        # Get the channel in this new context.
        channel = session.query(Channel).filter_by(id=channel.id).one()

        channel.info_json = info
        channel.info_date = now()
        channel.source_id = info.get('id')

        with get_db_curs() as curs:
            # Get all known videos in this channel.
            query = 'SELECT source_id FROM video WHERE channel_id=%s AND source_id IS NOT NULL'
            curs.execute(query, (channel.id,))
            known_source_ids = {i[0] for i in curs.fetchall()}

        new_source_ids = all_source_ids.difference(known_source_ids)

        logger.info(f'Got {len(new_source_ids)} new videos for channel {channel.name}')
        channel_id = channel.id
        for source_id in new_source_ids:
            url = urls.get(source_id)
            session.add(Video(source_id=source_id, channel_id=channel_id, url=url))

    # Write the Channel's info to a JSON file.
    if channel.directory:
        info_json_path = channel.directory.path / f'{channel.name}.info.json'
        with info_json_path.open('wt') as fh:
            json.dump(info, fh, indent=2)

    # Update all view counts using the latest from the Channel's info_json.
    apply_info_json(channel_id)


def _find_all_missing_videos(link: str = None) -> List[Tuple]:
    """Get all Video entries which don't have the required media files (i.e. hasn't been downloaded).

    Restrict to a single channel if "link" is provided.
    """
    with get_db_curs() as curs:
        # Get all channels by default.
        where = ''
        params = ()

        if link:
            # Restrict by channel when link is provided.
            query = 'SELECT id FROM channel WHERE link = %s'
            curs.execute(query, (link,))
            channel_id = curs.fetchall()[0][0]
            where = 'AND channel_id = %s'
            params = (channel_id,)

        query = f'''
            SELECT
                video.id, video.source_id, video.channel_id
            FROM
                video
                LEFT JOIN channel ON channel.id = video.channel_id
            WHERE
                channel.url IS NOT NULL
                AND channel.url != ''
                AND video.source_id IS NOT NULL
                {where}
                AND video.channel_id IS NOT NULL
                AND (video_path IS NULL OR video_path = '' OR poster_path IS NULL OR poster_path = '')
        '''
        logger.debug(query)
        curs.execute(query, params)
        missing_videos = list(curs.fetchall())
        return missing_videos


def find_all_missing_videos(link: str = None) -> Tuple[dict, dict]:
    """
    Find all videos that don't have a video file, but are found in the DB (taken from the channel's info_json).

    Yields a Channel Dict object, our Video id, and the "entry" of the video from the channel's info_json['entries'].
    """
    with get_db_session() as session:
        if link:
            try:
                channel = session.query(Channel).filter_by(link=link).one()
            except NoResultFound:
                raise UnknownChannel(f'No channel with link: {link}')
            if not channel.url:
                raise ChannelURLEmpty('No URL for this channel')
            channels = [channel, ]
        else:
            channels = session.query(Channel).filter(Channel.info_json != None).all()  # noqa

        # Get all channels while in the db context.
        channels = list(channels)

    # Check that each channel has some videos.  We can't be sure what is missing if we don't know what we have.
    for channel in channels:
        if channel.refreshed is False:
            # Refresh this channel's videos.
            refresh_channel_videos(channel)

    channels = {i.id: i for i in channels}

    match_regexen = {i: re.compile(j.match_regex) for i, j in channels.items() if j.match_regex}

    # Convert the channel video entries into a form that allows them to be quickly retrieved without searching through
    # the entire entries list.
    channels_entries = {}
    for id_, channel in channels.items():
        channels_entries[id_] = {i['id']: i for i in channel.info_json['entries']}

    missing_videos = _find_all_missing_videos(link)

    for id_, source_id, channel_id in missing_videos:
        channel = channels[channel_id]

        if channel.skip_download_videos and source_id in channel.skip_download_videos:
            # This video has been marked to skip.
            continue

        try:
            missing_video = channels_entries[channel_id][source_id]
        except KeyError:
            logger.warning(f'Video {id_} / {source_id} is not in {channel.name} info_json')
            continue

        match_regex: re.compile = match_regexen.get(channel_id)
        if not match_regex or (match_regex and missing_video['title'] and match_regex.match(missing_video['title'])):
            # No title match regex, or the title matches the regex.
            yield id_, source_id, missing_video


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
