#! /usr/bin/env python3
import json
import pathlib
import re
from datetime import datetime, timedelta, date
from queue import Queue
from random import shuffle
from typing import Tuple, List

from dictorm import DictDB, Dict, And, Or
from sqlalchemy.orm import Session
from youtube_dl import YoutubeDL

from api.common import logger, today, ProgressReporter, date_range
from api.db import get_db_context
from .captions import process_captions
from .common import get_downloader_config, get_absolute_media_path, add_video_to_skip_list
from .models import Video
from ..errors import UnknownChannel, ChannelURLEmpty
from ..vars import UNRECOVERABLE_ERRORS

logger = logger.getChild(__name__)
ydl_logger = logger.getChild('youtube-dl')

YDL = YoutubeDL()
YDL.params['logger'] = ydl_logger
YDL.add_default_info_extractors()


def update_channel(channel: Dict = None, link: str = None):
    """
    Connect to the Channel's host website and pull a catalog of all videos.  Insert any new videos into the DB.

    It is expected that any missing videos will be downloaded later.
    """
    with get_db_context() as (engine, session):
        if not channel:
            Channel = db['channel']
            channel = Channel.get_one(link=link)

    logger.info(f'Downloading video list for {channel["name"]} at {channel["url"]}  This may take several minutes.')
    info = YDL.extract_info(channel['url'], download=False, process=False)
    if 'url' in info:
        url = info['url']
        info = YDL.extract_info(url, download=False, process=False)

    # Resolve all entries to dictionaries.
    entries = info['entries'] = list(info['entries'])

    # Youtube-DL may hand back a list of URLs, lets use the "Uploads" URL, if available.
    try:
        entries[0]['id']
    except KeyError:
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
        Channel = db['channel']
        channel = Channel.get_one(id=channel['id'])

        download_frequency = channel['download_frequency']

        channel['info_json'] = info
        channel['info_date'] = datetime.now()
        channel['next_download'] = today() + timedelta(seconds=download_frequency)
        channel.flush()

        # Insert any new videos.
        curs = db_conn.cursor()
        query = 'SELECT source_id FROM video WHERE channel_id=%s AND source_id IS NOT NULL'
        curs.execute(query, (channel['id'],))
        known_source_ids = {i[0] for i in curs.fetchall()}

        new_source_ids = all_source_ids.difference(known_source_ids)

        logger.info(f'Got {len(new_source_ids)} new videos for channel {channel["name"]}')
        Video = db['video']
        channel_id = channel['id']
        for source_id in new_source_ids:
            Video(source_id=source_id, channel_id=channel_id).flush()


def update_channels(reporter: ProgressReporter, link: str = None):
    """Update all information for each channel.  (No downloads performed)"""

    with get_db_context() as (engine, session):
        Channel = db['channel']

        if Channel.count() == 0:
            raise UnknownChannel('No channels exist yet')

        if link:
            channel = Channel.get_one(link=link)
            if not channel:
                raise UnknownChannel(f'No channel with link: {link}')
            channels = [channel, ]
        else:
            channels = list(Channel.get_where(
                And(
                    Channel['url'].IsNotNull(),
                    Channel['url'] != '',
                    Or(
                        Channel['next_download'].IsNull(),
                        Channel['next_download'] <= today(),
                    )
                )
            ))

        if len(channels) == 0:
            logger.warning(f'All channels are up to date')

    reporter.set_progress_total(0, len(channels))
    reporter.send_progress(0, 0, f'{len(channels)} channels scheduled for update')

    # Randomize downloading of channels.
    shuffle(channels)

    logger.debug(f'Getting info for {len(channels)} channels')
    for idx, channel in enumerate(channels):
        reporter.send_progress(0, idx, f'Getting video list for {channel["name"]}')
        try:
            update_channel(channel)
        except Exception:
            logger.critical('Unable to fetch channel videos', exc_info=True)
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
    with get_db_context() as (engine, session):
        curs = db_conn.cursor()

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


def find_all_missing_videos(link: str = None) -> Tuple[Dict, dict]:
    """
    Find all videos that don't have a video file, but are found in the DB (taken from the channel's info_json).

    Yields a Channel Dict object, our Video id, and the "entry" of the video from the channel's info_json['entries'].
    """
    with get_db_context() as (engine, session):
        Channel = db['channel']

        if link:
            channel = Channel.get_one(link=link)
            if not channel:
                raise UnknownChannel(f'No channel with link: {link}')
            if not channel['url']:
                raise ChannelURLEmpty('No URL for this channel')
            channels = [channel, ]
        else:
            channels = Channel.get_where(Channel['info_json'].IsNotNull())

        # Get all channels while in the db context.
        channels = list(channels)

    channels = {i['id']: i for i in channels}

    match_regexen = {i: re.compile(j['match_regex']) for i, j in channels.items() if j['match_regex']}

    # Convert the channel video entries into a form that allows them to be quickly retrieved without searching through
    # the entire entries list.
    channels_entries = {}
    for id_, channel in channels.items():
        channels_entries[id_] = {i['id']: i for i in channel['info_json']['entries']}

    missing_videos = _find_all_missing_videos(link)

    for id_, source_id, channel_id in missing_videos:
        channel = channels[channel_id]

        if channel['skip_download_videos'] and source_id in channel['skip_download_videos']:
            # This video has been marked to skip.
            continue

        try:
            missing_video = channels_entries[channel_id][source_id]
        except KeyError:
            logger.warning(f'Video {id_} / {source_id} is not in {channel["name"]} info_json')
            continue

        match_regex: re.compile = match_regexen.get(channel_id)
        if not match_regex or (match_regex and missing_video['title'] and match_regex.match(missing_video['title'])):
            # No title match regex, or the title matches the regex.
            yield channel, id_, missing_video


def download_video(channel: dict, video: dict) -> pathlib.Path:
    """
    Download a video (and associated posters/etc) to it's channel's directory.

    :param channel: A DictORM Channel entry
    :param video: A YoutubeDL info entry dictionary
    :return:
    """
    # YoutubeDL expects specific options, add onto the default options
    config = get_downloader_config()
    options = dict(config)
    directory = get_absolute_media_path(channel['directory'])
    options['outtmpl'] = f'{directory}/{config["file_name_format"]}'

    ydl = YoutubeDL(options)
    ydl.add_default_info_extractors()
    source_id = video['id']
    url = f'https://www.youtube.com/watch?v={source_id}'
    entry = ydl.extract_info(url, download=True, process=True)
    final_filename = ydl.prepare_filename(entry)
    final_filename = pathlib.Path(final_filename)
    return final_filename


def find_meta_files(path: pathlib.Path, relative_to=None) -> Tuple[
    pathlib.Path, pathlib.Path, pathlib.Path, pathlib.Path]:
    """
    Find all files that share a file's full path, except their extensions.  It is assumed that file with the
    same name, but different extension is related to that file.  A None will be yielded if the meta file doesn't exist.

    Example:
        >>> foo = pathlib.Path('foo.bar')
        >>> find_meta_files(foo)
        (pathlib.Path('foo.jpg'), pathlib.Path('foo.description'),
        pathlib.Path('foo.en.vtt'), pathlib.Path('foo.info.json'))
    """
    suffix = path.suffix
    name, suffix, _ = str(path.name).rpartition(suffix)
    meta_file_exts = (('.jpg', '.webp', '.png'), ('.description',), ('.en.vtt', '.en.srt'), ('.info.json',))
    for meta_exts in meta_file_exts:
        for meta_ext in meta_exts:
            meta_path = path.with_suffix(meta_ext)
            if meta_path.exists():
                if relative_to:
                    yield meta_path.relative_to(relative_to)
                    break
                else:
                    yield meta_path
                    break
        else:
            yield None


NAME_PARSER = re.compile(r'(.*?)_((?:\d+?)|(?:NA))_(?:(.{11})_)?(.*)\.'
                         r'(jpg|webp|flv|mp4|part|info\.json|description|webm|..\.srt|..\.vtt)')


def upsert_video(session: Session, video_path: pathlib.Path, channel: Dict, idempotency: str = None, skip_captions=False,
                 id_: str = None) -> Dict:
    """
    Insert a video into the DB.  Also, find any meta-files near the video file and store them on the video row.

    If id_ is provided, update that entry.
    """
    channel_dir = get_absolute_media_path(channel['directory'])
    poster_path, description_path, caption_path, info_json_path = find_meta_files(video_path, relative_to=channel_dir)

    # Video paths should be relative to the channel's directory
    if video_path.is_absolute():
        video_path = video_path.relative_to(channel_dir)

    name_match = NAME_PARSER.match(video_path.name)
    _ = upload_date = source_id = title = ext = None
    if name_match:
        _, upload_date, source_id, title, ext = name_match.groups()

    # Make sure the date is a valid date format, if not, leave it blank.  Youtube-DL sometimes puts an NA in the date.
    # We may even get videos that weren't downloaded by WROLPi.
    if not upload_date or not upload_date.isdigit() or len(upload_date) != 8:
        logger.debug(f'Could not parse date from filename: {video_path}')
        upload_date = None

    duration = None
    if info_json_path:
        path = (channel_dir / info_json_path).absolute()
        try:
            with open(path) as fh:
                json_contents = json.load(fh)
                duration = json_contents['duration']
        except json.decoder.JSONDecodeError:
            logger.warning(f'Failed to load JSON file to get duration: {path}')

    video_dict = dict(
        channel_id=channel['id'],
        description_path=str(description_path) if description_path else None,
        ext=ext,
        poster_path=str(poster_path) if poster_path else None,
        source_id=source_id,
        title=title,
        upload_date=upload_date,
        video_path=str(video_path),
        name=video_path.name,
        caption_path=str(caption_path) if caption_path else None,
        idempotency=idempotency,
        info_json_path=str(info_json_path) if info_json_path else None,
        downloaded=True if video_path else False,
        duration=duration,
    )

    if id_:
        video = session.query(Video).filter(id=id_).one()
        video.update(video_dict)
    else:
        video = Video(**video_dict)

    session.flush(video)

    if skip_captions is False and caption_path:
        # Process captions only when requested
        process_captions(video)

    return video


def _skip_download(error):
    """Return True if the error is unrecoverable and the video should be skipped in the future."""
    error_str = str(error)
    for msg in UNRECOVERABLE_ERRORS:
        if msg in error_str:
            return True
    return False


def download_all_missing_videos(reporter: ProgressReporter, link: str = None):
    """Find any videos identified by the info packet that haven't yet been downloaded, download them."""
    missing_videos = list(find_all_missing_videos(link))
    reporter.set_progress_total(1, len(missing_videos))
    reporter.message(1, f'Found {len(missing_videos)} missing videos.')

    for idx, (channel, id_, missing_video) in enumerate(missing_videos):
        reporter.send_progress(1, idx, f'Downloading {channel["name"]}: {missing_video["title"]}')
        try:
            video_path = download_video(channel, missing_video)
        except Exception as e:
            logger.warning(f'Failed to download "{missing_video["title"]}" with exception: {e}')
            if _skip_download(e):
                # The video failed to download, and the error will never be fixed.  Skip it forever.
                source_id = missing_video.get('id')
                logger.warning(f'Adding video "{source_id}" to skip list for this channel.  WROLPi will not '
                               f'attempt to download it again.')

                with get_db_context(commit=True) as (engine, session):
                    channel = db['channel'].get_one(id=channel['id'])
                    add_video_to_skip_list(channel, {'source_id': source_id})

            reporter.error(1, f'Failed to download "{missing_video["title"]}", see server logs...')
            continue
        with get_db_context(commit=True) as (engine, session):
            upsert_video(db, video_path, channel, id_=id_)

    reporter.finish(1, 'All videos are downloaded')


def distribute_download_days(start: date = None):
    common_frequency = {}

    # Start distributing on the day provided, or start today.
    start = start or today()

    with get_db_context(commit=True) as (engine, session):
        Channel = db['channel']
        # Sort channels by their download frequency.
        for channel in Channel.get_where(Channel['next_download'].IsNotNull()):
            download_frequency = channel['download_frequency']
            try:
                common_frequency[download_frequency].append(channel)
            except KeyError:
                common_frequency[download_frequency] = [channel, ]

        for frequency, channels in common_frequency.items():
            last_day = start + timedelta(seconds=frequency)
            date_ranges = iter(date_range(start, last_day, len(channels)))
            for channel in channels:
                channel['next_download'] = next(date_ranges)
                channel.flush()


def main(args=None):
    """Find and download any missing videos.  Parse any arguments passed by the cmd-line."""
    q = Queue()
    reporter = ProgressReporter(q, 2)
    for status in update_channels(reporter):
        logger.info(str(status))
    download_all_missing_videos(reporter)
    return 0
