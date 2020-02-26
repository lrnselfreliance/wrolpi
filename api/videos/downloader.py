#! /usr/bin/env python3
import glob
import pathlib
import re
from datetime import datetime
from typing import Tuple, List

import psycopg2
from dictorm import DictDB, Dict
from youtube_dl import YoutubeDL

from api.common import make_progress_calculator, logger
from api.db import get_db_context
from .captions import process_captions
from .common import get_downloader_config, get_absolute_media_path, replace_extension

logger = logger.getChild('api:downloader')
ydl_logger = logger.getChild('api:youtube-dl')

YDL = YoutubeDL()
YDL.params['logger'] = ydl_logger
YDL.add_default_info_extractors()


def update_channel(db_conn: psycopg2.connect, db: DictDB, channel: Dict = None, link: str = None):
    """
    Connect to the Channel's host website and pull a catalog of all videos.  Insert any new videos into the DB.

    It is expected that any missing videos will be downloaded later.
    """
    if not channel:
        Channel = db['channel']
        channel = Channel.get_one(link=link)

    with db.transaction(commit=True):
        logger.info(f'Downloading video list for {channel["url"]}  This may take several minutes.')
        info = YDL.extract_info(channel['url'], download=False, process=False)
        if 'url' in info:
            url = info['url']
            info = YDL.extract_info(url, download=False, process=False)

        # Resolve all entries to dictionaries.
        entries = info['entries'] = list(info['entries'])

        channel['info_json'] = info
        channel['info_date'] = datetime.now()
        channel.flush()

        # This is all the source id's that are currently available.
        all_source_ids = {i['id'] for i in entries}

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


def update_channels(db_conn, db):
    """Update all information for each channel.  (No downloads performed)"""
    Channel = db['channel']

    channels = list(Channel.get_where())
    logger.debug(f'Getting info for {len(channels)} channels')
    calc_progress = make_progress_calculator(len(channels))
    for idx, channel in enumerate(channels):
        yield {'progress': calc_progress(idx), 'message': f'Getting video list for {channel["name"]}'}
        update_channel(db_conn, db, channel)

    yield {'progress': 100, 'message': 'All video lists updated.'}


VIDEO_EXTENSIONS = ['mp4', 'webm', 'flv']


def find_matching_video_files(directory, search_str) -> str:
    """Create a generator which returns any video files containing the search string."""
    for ext in VIDEO_EXTENSIONS:
        yield from glob.glob(f'{directory}/*{search_str}*{ext}')


def find_missing_channel_videos(db: DictDB, channel: Dict) -> dict:
    """
    Search a Channel's directory for any videos that are in the Channel's catalog, but not in the filesystem.  This
    means that the video is available for download, but has not yet been downloaded.  This function speeds up future
    searches by marking Video['downloaded'] = True for every video in a Channel not returned by this function.
    """
    info_json = channel['info_json']
    entries = info_json['entries']

    directory = get_absolute_media_path(channel['directory'])
    skip_download_videos = channel['skip_download_videos'] or []

    # Compare the available videos to what has been marked as downloaded.
    # Skip any videos that have been marked to skip.
    Video = db['video']
    downloaded_videos = channel['videos'].refine(Video['downloaded'].Is(True))
    downloaded_videos = [v['source_id'] for v in downloaded_videos]
    entries = [e for e in entries if e['id'] not in downloaded_videos and e['id'] not in skip_download_videos]

    found_entries = []
    for entry in entries:
        source_id = entry['id']
        matching_video_files = find_matching_video_files(directory, source_id)
        try:
            next(matching_video_files)
            # Some video file was found, move onto the next
            found_entries.append(source_id)
            continue
        except StopIteration:
            pass

        # No match for this entry, check if the title matches the channel regex
        if channel['match_regex'] and re.match(channel['match_regex'], entry['title']):
            yield entry
        elif channel['match_regex']:
            logger.debug(f'Skipping "{entry["title"]}", title does not match regex.')
        else:
            # No matches and no regex, download it
            yield entry

    # Mark the found entries as downloaded.
    if found_entries:
        query = 'UPDATE video SET downloaded=true WHERE source_id = ANY(%s)'
        db.curs.execute(query, (found_entries,))


def get_channel_video_count(channel: Dict) -> int:
    """Count all video files in a channel's directory."""
    return len(list(find_matching_video_files(channel['directory'], '')))


def _find_all_missing_videos(db_conn: psycopg2.connect) -> List[Tuple]:
    curs = db_conn.cursor()
    query = '''
        SELECT
            id, source_id, channel_id
        FROM video
        WHERE
            source_id IS NOT NULL
            AND channel_id IS NOT NULL
            AND (video_path IS NULL OR video_path = '')
    '''
    curs.execute(query)
    missing_videos = list(curs.fetchall())
    return missing_videos


def _count_missing_videos(db_conn: psycopg2.connect):
    curs = db_conn.cursor()
    query = '''
        SELECT
            COUNT(id)
        FROM video
        WHERE
            source_id IS NOT NULL
            AND channel_id IS NOT NULL
            AND (video_path IS NULL OR video_path = '')
    '''
    curs.execute(query)
    return int(curs.fetchone()[0])


def find_all_missing_videos(db_conn: psycopg2.connect, db: DictDB) -> Tuple[Dict, dict]:
    """
    Find all videos that don't have a video file, but are found in the DB (taken from the channel's info_json).

    Yields a Channel Dict object, and the "entry" of the video from the channel's info_json['entries'].
    """
    Channel = db['channel']
    channels = Channel.get_where(Channel['info_json'].IsNotNull())
    channels = {i['id']: i for i in channels}

    match_regexes = {i: re.compile(j['match_regex']) for i, j in channels.items() if j['match_regex']}

    # Convert the channel video entries into a form that allows them to be quickly retrieved without searching through
    # the entire entries list.
    channels_entries = {}
    for id_, channel in channels.items():
        channels_entries[id_] = {i['id']: i for i in channel['info_json']['entries']}

    missing_videos = _find_all_missing_videos(db_conn)

    for id_, source_id, channel_id in missing_videos:
        channel = channels[channel_id]
        missing_video = channels_entries[channel_id][source_id]
        match_regex: re.compile = match_regexes.get(channel_id)
        if not match_regex or (match_regex and match_regex.match(missing_video['title'])):
            # No title match regex, or the title matches the regex.
            yield channel, id_, missing_video


def download_video(channel: dict, video: dict) -> pathlib.Path:
    """
    Download a video (and associated thumbnail/etc) to it's channel's directory.

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
        pathlib.Path('foo.jpg'), pathlib.Path('foo.info.json'))
    """
    suffix = path.suffix
    name, suffix, _ = str(path.name).rpartition(suffix)
    meta_file_exts = (('.jpg',), ('.description',), ('.en.vtt', '.en.srt'), ('.info.json',))
    for meta_exts in meta_file_exts:
        for meta_ext in meta_exts:
            meta_path = replace_extension(path, meta_ext)
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
                         r'(jpg|flv|mp4|part|info\.json|description|webm|..\.srt|..\.vtt)')


def upsert_video(db: DictDB, video_path: pathlib.Path, channel: Dict, idempotency: str = None,
                 skip_captions=False, id_: str = None) -> Dict:
    """
    Insert a video into the DB.  Also, find any meta-files near the video file and store them on the video row.

    If id_ is provided, update that entry.
    """
    Video = db['video']
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
    )

    if id_:
        video = Video.get_one(id=id_)
        video.update(video_dict)
    else:
        video = Video(**video_dict)

    video.flush()

    if skip_captions is False and caption_path:
        # Process captions only when requested
        process_captions(video)

    return video


def _skip_download(error):
    """Return True if the error is unrecoverable and the video should be skipped in the future."""
    if 'requires payment' in str(error):
        return True
    elif 'Content Warning' in str(error):
        return True
    elif 'Did not get any data blocks' in str(error):
        return True
    return False


def download_all_missing_videos(db_conn, db):
    """Find any videos identified by the info packet that haven't yet been downloaded, download them."""
    yield {'progress': 0, 'message': 'Comparing local videos to available videos...'}
    missing_videos = list(find_all_missing_videos(db_conn, db))

    missing_videos_count = _count_missing_videos(db_conn)
    calc_progress = make_progress_calculator(missing_videos_count)

    for index, (channel, id_, missing_video) in enumerate(missing_videos):
        try:
            video_path = download_video(channel, missing_video)
        except Exception as e:
            logger.warning(f'Failed to download "{missing_video["title"]}" with exception: {e}')
            if _skip_download(e):
                # The video failed to download, and the error will never be fixed.  Skip it forever.
                skip_download_videos = channel['skip_download_videos']
                source_id = missing_video.get('id')
                logger.warning(f'Adding video "{source_id}" to skip list for this channel.  WROLPi will not '
                               f'attempt to download it again.')
                if skip_download_videos and source_id:
                    channel['skip_download_videos'].append(missing_video['id'])
                elif source_id:
                    channel['skip_download_videos'] = [missing_video['id'], ]
                channel.flush()
                db_conn.commit()

            yield f'Failed to download "{missing_video["title"]}", see logs...'
            continue
        upsert_video(db, video_path, channel, id_=id_)
        yield {'progress': calc_progress(index), 'message': f'{channel["name"]}: Downloaded: {missing_video["title"]}'}
        db_conn.commit()

    yield {'progress': 100, 'message': 'All videos are downloaded'}


def main(args=None):
    """Find and download any missing videos.  Parse any arguments passed by the cmd-line."""
    with get_db_context(commit=True) as (db_conn, db):
        for status in update_channels(db_conn, db):
            logger.info(str(status))
        for status in download_all_missing_videos(db_conn, db):
            logger.info(status)
    return 0
