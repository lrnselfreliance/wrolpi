#! /usr/bin/env python3
import pathlib
import re
from queue import Queue
from random import shuffle
from typing import Tuple, List

from sqlalchemy import or_
from sqlalchemy.orm.exc import NoResultFound
from youtube_dl import YoutubeDL

from api.common import logger, today, ProgressReporter, now, run_after
from api.db import get_db_context, get_db_curs
from .common import load_downloader_config, get_absolute_media_path
from .lib import save_channels_config, upsert_video
from .models import Video, Channel
from ..errors import UnknownChannel, ChannelURLEmpty
from ..vars import UNRECOVERABLE_ERRORS

logger = logger.getChild(__name__)
ydl_logger = logger.getChild('youtube-dl')

YDL = YoutubeDL()
YDL.params['logger'] = ydl_logger
YDL.add_default_info_extractors()


def update_channel(channel=None, link: str = None):
    """
    Connect to the Channel's host website and pull a catalog of all videos.  Insert any new videos into the DB.

    It is expected that any missing videos will be downloaded later.
    """
    with get_db_context() as (engine, session):
        if not channel:
            channel = session.query(Channel).filter_by(link=link).one()

    logger.info(f'Downloading video list for {channel.name} at {channel.url}  This may take several minutes.')
    info = YDL.extract_info(channel.url, download=False, process=False)
    if 'url' in info:
        url = info['url']
        info = YDL.extract_info(url, download=False, process=False)

    # Resolve all entries to dictionaries.
    entries = info['entries'] = list(info['entries'])

    # Youtube-DL may hand back a list of URLs, lets use the "Uploads" URL, if available.
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

    with get_db_context(commit=True) as (engine, session):
        # Get the channel in this new context.
        channel = session.query(Channel).filter_by(id=channel.id).one()

        channel.info_json = info
        channel.info_date = now()
        channel.increment_next_download()

        with get_db_curs() as curs:
            # Insert any new videos.
            query = 'SELECT source_id FROM video WHERE channel_id=%s AND source_id IS NOT NULL'
            curs.execute(query, (channel.id,))
            known_source_ids = {i[0] for i in curs.fetchall()}

        new_source_ids = all_source_ids.difference(known_source_ids)

        logger.info(f'Got {len(new_source_ids)} new videos for channel {channel.name}')
        channel_id = channel.id
        for source_id in new_source_ids:
            session.add(Video(source_id=source_id, channel_id=channel_id))


def update_channels(reporter: ProgressReporter, link: str = None):
    """Update all information for each channel.  (No downloads performed)"""

    with get_db_context() as (engine, session):
        if session.query(Channel).count() == 0:
            raise UnknownChannel('No channels exist yet')

        if link:
            try:
                channel = session.query(Channel).filter_by(link=link).one()
            except NoResultFound:
                raise UnknownChannel(f'No channel with link: {link}')
            channels = [channel, ]
        else:
            channels = session.query(Channel).filter(
                Channel.url != None,  # noqa
                Channel.url != '',
                or_(
                    Channel.next_download == None,  # noqa
                    Channel.next_download <= today(),
                )
            ).all()

        if len(channels) == 0:
            logger.warning(f'All channels are up to date')

    reporter.set_progress_total(0, len(channels))
    reporter.send_progress(0, 0, f'{len(channels)} channels scheduled for update')

    # Randomize downloading of channels.
    shuffle(channels)

    logger.debug(f'Getting info for {len(channels)} channels')
    for idx, channel in enumerate(channels):
        reporter.send_progress(0, idx, f'Getting video list for {channel.name}')
        try:
            update_channel(channel)
        except Exception:
            logger.critical(f'Unable to get video list for {channel.name}', exc_info=True)
            continue

    if channels:
        reporter.send_progress(0, len(channels), 'Done downloading video lists')
    else:
        reporter.finish(0, 'Done downloading video lists')


def _find_all_missing_videos(link: str = None) -> List[Tuple]:
    """
    Get all Video entries which don't have the required media files (i.e. hasn't been downloaded).  Restrict to a
    single channel if "link" is provided.
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
                AND source_id IS NOT NULL
                {where}
                AND channel_id IS NOT NULL
                AND (video_path IS NULL OR video_path = '' OR poster_path IS NULL OR poster_path = '')
        '''
        curs.execute(query, params)
        missing_videos = list(curs.fetchall())
        return missing_videos


def find_all_missing_videos(link: str = None) -> Tuple[dict, dict]:
    """
    Find all videos that don't have a video file, but are found in the DB (taken from the channel's info_json).

    Yields a Channel Dict object, our Video id, and the "entry" of the video from the channel's info_json['entries'].
    """
    with get_db_context() as (engine, session):
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
            yield channel, id_, missing_video


def download_video(channel: Channel, video: dict) -> pathlib.Path:
    """
    Download a video (and associated posters/etc) to it's channel's directory.

    :param channel:
    :param video: A YoutubeDL info entry dictionary
    :return:
    """
    # YoutubeDL expects specific options, add onto the default options
    config = load_downloader_config()
    options = dict(config)
    directory = get_absolute_media_path(channel.directory)
    options['outtmpl'] = f'{directory}/{config["file_name_format"]}'

    ydl = YoutubeDL(options)
    ydl.add_default_info_extractors()
    source_id = video['id']
    url = f'https://www.youtube.com/watch?v={source_id}'
    entry = ydl.extract_info(url, download=True, process=True)
    final_filename = ydl.prepare_filename(entry)
    final_filename = pathlib.Path(final_filename)
    return final_filename


def _skip_download(error):
    """Return True if the error is unrecoverable and the video should be skipped in the future."""
    error_str = str(error)
    for msg in UNRECOVERABLE_ERRORS:
        if msg in error_str:
            return True
    return False


@run_after(save_channels_config)
def download_all_missing_videos(reporter: ProgressReporter, link: str = None):
    """Find any videos identified by the info packet that haven't yet been downloaded, download them."""
    missing_videos = list(find_all_missing_videos(link))
    reporter.set_progress_total(1, len(missing_videos))
    reporter.message(1, f'Found {len(missing_videos)} missing videos.')

    for idx, (channel, id_, missing_video) in enumerate(missing_videos):
        reporter.send_progress(1, idx, f'Downloading {channel.name}: {missing_video["title"]}')
        try:
            video_path = download_video(channel, missing_video)
        except Exception as e:
            logger.warning(f'Failed to download "{missing_video["title"]}"', exc_info=e)
            if _skip_download(e):
                # The video failed to download, and the error will never be fixed.  Skip it forever.
                source_id = missing_video.get('id')
                logger.warning(f'Adding video "{source_id}" to skip list for this channel.  WROLPi will not '
                               f'attempt to download it again.')

                with get_db_context(commit=True) as (engine, session):
                    channel = session.query(Channel).filter_by(id=channel.id).one()
                    channel.add_video_to_skip_list(source_id)

            reporter.error(1, f'Failed to download "{missing_video["title"]}", see server logs...')
            continue

        with get_db_context(commit=True) as (engine, session):
            upsert_video(session, video_path, channel, id_=id_)

    reporter.finish(1, 'All videos are downloaded')


def main(args=None):
    """Find and download any missing videos.  Parse any arguments passed by the cmd-line."""
    q = Queue()
    reporter = ProgressReporter(q, 2)
    update_channels(reporter)
    download_all_missing_videos(reporter)
    return 0
