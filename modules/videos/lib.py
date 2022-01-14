import html
import json
import pathlib
import re
from collections import defaultdict
from typing import Tuple
from uuid import uuid1

from sqlalchemy.orm import Session

from wrolpi.common import logger, chunks, get_config
from wrolpi.common import save_settings_config
from wrolpi.db import get_db_curs, get_db_session, optional_session
from wrolpi.media_path import MediaPath
from wrolpi.vars import PYTEST
from .captions import get_video_captions
from .common import generate_video_paths, remove_duplicate_video_paths, apply_info_json, import_videos_config, \
    get_video_duration, is_valid_poster, convert_image, generate_video_poster
from .models import Channel, Video

logger = logger.getChild(__name__)

DEFAULT_DOWNLOAD_FREQUENCY = 60 * 60 * 24 * 7  # weekly


def refresh_channel_videos(channel: Channel):
    """
    Find all video files in a channel's directory.  Add any videos not in the DB to the DB.
    """
    # Set the idempotency key so we can remove any videos not touched during this search
    with get_db_curs(commit=True) as curs:
        curs.execute('UPDATE video SET idempotency=NULL WHERE channel_id=%s', (channel.id,))

    idempotency = str(uuid1())
    directory = channel.directory.path

    # A set of absolute paths that exist in the file system
    possible_new_paths = generate_video_paths(directory)
    possible_new_paths = remove_duplicate_video_paths(possible_new_paths)

    # Update all videos that match the current video paths
    new_paths = [str(i) for i in possible_new_paths]
    with get_db_curs(commit=True) as curs:
        query = 'UPDATE video SET idempotency = %s WHERE channel_id = %s AND video_path = ANY(%s) RETURNING video_path'
        curs.execute(query, (idempotency, channel.id, new_paths))
        existing_paths = {i for (i,) in curs.fetchall()}

    # Get the paths for any video not yet in the DB
    # (paths in DB are relative, but we need to pass an absolute path)
    new_videos = {i for i in possible_new_paths if str(i) not in existing_paths}

    for chunk in chunks(new_videos, 20):
        with get_db_session(commit=True) as session:
            for video_path in chunk:
                video_path = pathlib.Path(video_path)
                upsert_video(session, video_path, channel, idempotency=idempotency)
                logger.debug(f'{channel.name}: Added {video_path.name}')

    with get_db_curs(commit=True) as curs:
        curs.execute('DELETE FROM video WHERE channel_id=%s AND idempotency IS NULL RETURNING id', (channel.id,))
        deleted_count = len(curs.fetchall())

    if deleted_count:
        deleted_status = f'Deleted {deleted_count} video records from channel {channel.name}'
        logger.info(deleted_status)

    logger.info(f'{channel.name}: {len(new_videos)} new videos, {len(existing_paths)} already existed. ')

    channel.refreshed = True
    Session.object_session(channel).commit()

    apply_info_json(channel.id)


def refresh_no_channel_videos():
    """
    Refresh the Videos in the NO CHANNEL directory.
    """
    from modules.videos.downloader import get_no_channel_directory
    directory = get_no_channel_directory()
    if not directory.is_dir():
        return

    logger.info('Refreshing NO CHANNEL videos')

    idempotency = str(uuid1())

    # Get all WROLPi compatible videos, remove any duplicates (different formats).
    possible_new_paths = generate_video_paths(directory)
    possible_new_paths = remove_duplicate_video_paths(possible_new_paths)

    new_paths = [str(i) for i in possible_new_paths]
    with get_db_curs(commit=True) as curs:
        query = 'UPDATE video SET idempotency = %s WHERE video_path = ANY(%s) RETURNING video_path'
        curs.execute(query, (idempotency, new_paths))
        existing_paths = {i for (i,) in curs.fetchall()}

    new_videos = {i for i in possible_new_paths if str(i) not in existing_paths}

    for chunk in chunks(new_videos, 20):
        with get_db_session(commit=True) as session:
            for video_path in chunk:
                upsert_video(session, pathlib.Path(video_path), idempotency=idempotency)
                logger.debug(f'Added NO CHANNEL video {video_path}')

    with get_db_curs(commit=True) as curs:
        curs.execute('DELETE FROM video WHERE channel_id IS NULL AND idempotency IS NULL RETURNING id')
        deleted_count = len(curs.fetchall())

    if deleted_count:
        deleted_status = f'Deleted {deleted_count} video records in NO CHANNEL.'
        logger.info(deleted_status)


def process_video_info_json(video: Video):
    """
    Parse the Video's info json file, return the relevant data.
    """
    title = duration = view_count = url = None
    if info_json := video.get_info_json():
        title = info_json.get('fulltitle') or info_json.get('title')
        title = html.unescape(title) if title else None

        duration = info_json.get('duration')
        view_count = info_json.get('view_count')
        url = info_json.get('webpage_url') or info_json.get('url')

    return title, duration, view_count, url


def validate_videos():
    """
    Validate all Videos not yet validated.  A Video is validated when we have attempted to find its: title, duration,
    view_count, url, caption, size.  A Video is also valid when it has a JPEG poster, if any.  If no poster can be
    found, it will be generated from the video file.

    This function marks the Video as validated, even if no data can be found so a Video will not be validated multiple
    times.
    """
    with get_db_curs() as curs:
        curs.execute('SELECT id FROM video WHERE video_path IS NOT NULL AND validated IS FALSE')
        video_ids = [i['id'] for i in curs.fetchall()]

    logger.info(f'Validating {len(video_ids)} videos.')
    for chunk in chunks(video_ids, 20):
        with get_db_session(commit=True) as session:
            videos = session.query(Video).filter(Video.id.in_(chunk)).all()
            for video in videos:
                try:
                    if not video.title or not video.duration or not video.view_count or not video.url:
                        # These properties can be found in the info json.
                        title, duration, view_count, url = process_video_info_json(video)
                        video.title = title
                        video.duration = duration
                        video.url = url
                        # View count will probably be overwritten by more recent data when this Video's Channel is
                        # updated.
                        video.view_count = view_count

                    if not video.title:
                        # Video title was not in the info json, use the filename.
                        title = video.video_path.path.with_suffix('').name
                        video.title = html.unescape(title)
                    if not video.duration:
                        # Video duration was not in the info json, use ffprobe.
                        video.duration = get_video_duration(video.video_path.path)

                    if not video.caption and video.caption_path:
                        video.caption = get_video_captions(video)
                    if not video.size:
                        video.size = video.video_path.path.stat().st_size

                    if not video.poster_path:
                        # Video poster is not found, lets check near the video file.
                        video_path = video.video_path.path
                        for ext in ('.jpg', '.jpeg', '.webp', '.png'):
                            if (poster_path := video_path.with_suffix(ext)).is_file():
                                video.poster_path = poster_path
                                break
                    if video.poster_path:
                        # Check that the poster is a more universally supported JPEG.
                        old: pathlib.Path = video.poster_path.path if \
                            isinstance(video.poster_path, MediaPath) else video.poster_path
                        new = old.with_suffix('.jpg')

                        if old != new and new.exists():
                            # Destination JPEG already exists (it may have the wrong format).
                            old.unlink()
                            old = video.poster_path = new

                        if not is_valid_poster(old):
                            # Poster is not valid, convert it and place it in the new location.
                            try:
                                convert_image(old, new)
                                old.unlink(missing_ok=True)
                                video.poster_path = new
                                logger.info(f'Converted invalid poster {old} to {new}')
                            except Exception as e:
                                logger.error(f'Failed to convert invalid poster {old} to {new}', exc_info=e)
                        else:
                            logger.debug(f'Poster was already valid: {new}')
                    if not video.poster_path:
                        # Video poster was not discovered, or converted.  Let's generate it.
                        try:
                            generate_video_poster(video_path)
                            video.poster_path = video_path.with_suffix('.jpg')
                            logger.debug(f'Generated poster for {video}')
                        except Exception as e:
                            logger.error(f'Failed to generate poster for {video}', exc_info=e)

                    # All data about the Video has been found, we should not attempt to validate it again.
                    video.validated = True
                except Exception as e:
                    # This video failed to validate, continue validation for the rest of the videos.
                    logger.warning(f'Failed to validate {video=}', exc_info=e)


def _refresh_videos(channel_links: list = None):
    """
    Find any videos in the channel directories and add them to the DB.  Delete DB records of any videos not in the
    file system.

    Yields status updates to be passed to the UI.

    :return:
    """
    logger.info('Refreshing video files')
    with get_db_session() as session:
        if channel_links:
            channels = session.query(Channel).filter(Channel.link.in_(channel_links))
        else:
            channels = session.query(Channel).all()

        channels = list(channels)

    if not channels and channel_links:
        raise Exception(f'No channels match links(s): {channel_links}')
    elif not channels:
        raise Exception(f'No channels in DB.  Have you created any?')

    for channel in channels:
        try:
            refresh_channel_videos(channel)
        except Exception as e:
            logger.fatal(f'Failed to refresh videos for channel {channel.name}!', exc_info=e)
            pass

    if not channel_links:
        # Refresh NO CHANNEL videos when not refreshing a specific channel.
        refresh_no_channel_videos()

    # Fill in any missing data for all videos.
    if not PYTEST:
        import_videos_config()
        validate_videos()


def get_channels_config(session: Session) -> dict:
    """
    Create a dictionary that contains all the Channels from the DB.
    """
    channels = session.query(Channel).order_by(Channel.link).all()
    channels = {i.link: i.config_view() for i in channels}

    # Get all Videos that are favorites.  Store them in their own config section, so they can be preserved if a channel
    # is deleted or the DB is wiped.
    favorite_videos = session.query(Video).filter(Video.favorite != None, Video.video_path != None).all()  # noqa
    favorites = defaultdict(lambda: {})
    for video in favorite_videos:
        if video.channel:
            favorites[video.channel.link][video.video_path.path.name] = dict(favorite=video.favorite)
        else:
            favorites['NO CHANNEL'][video.video_path.path.name] = dict(favorite=video.favorite)
    favorites = dict(favorites)

    return dict(channels=channels, favorites=favorites)


@optional_session()
def save_channels_config(session=None, preserve_favorites: bool = True):
    """
    Pull the Channel information from the DB, save it to the config.
    """
    config = get_channels_config(session)
    if preserve_favorites:
        config['favorites'].update(get_config().get('favorites', {}))
    save_settings_config(config)


async def get_statistics():
    with get_db_curs() as curs:
        curs.execute('''
        SELECT
            -- total videos
            COUNT(id) AS "videos",
            -- total videos that are marked as favorite
            COUNT(id) FILTER (WHERE favorite IS NOT NULL) AS "favorites",
            -- total videos downloaded over the past week/month/year
            COUNT(id) FILTER (WHERE upload_date >= current_date - interval '1 week') AS "week",
            COUNT(id) FILTER (WHERE upload_date >= current_date - interval '1 month') AS "month",
            COUNT(id) FILTER (WHERE upload_date >= current_date - interval '1 year') AS "year",
            -- sum of all video lengths in seconds
            COALESCE(SUM(duration), 0) AS "sum_duration",
            -- sum of all video file sizes
            COALESCE(SUM(size), 0)::BIGINT AS "sum_size",
            -- largest video
            COALESCE(MAX(size), 0) AS "max_size"
        FROM
            video
        WHERE
            video_path IS NOT NULL
        ''')
        video_stats = dict(curs.fetchone())

        # Get the total videos downloaded every month for the past two years.
        curs.execute('''
        SELECT
            DATE_TRUNC('month', months.a),
            COUNT(id)::BIGINT,
            SUM(size)::BIGINT AS "size"
        FROM
            generate_series(
                date_trunc('month', current_date) - interval '2 years',
                date_trunc('month', current_date) - interval '1 month',
                '1 month'::interval) AS months(a),
            video
        WHERE
            video.upload_date >= date_trunc('month', months.a)
            AND video.upload_date < date_trunc('month', months.a) + interval '1 month'
            AND video.upload_date IS NOT NULL
            AND video.video_path IS NOT NULL
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
            COUNT(id) AS "channels"
        FROM
            channel
        ''')
        channel_stats = dict(curs.fetchone())
    ret = dict(statistics=dict(
        videos=video_stats,
        channels=channel_stats,
        historical=historical_stats,
    ))
    return ret


NAME_PARSER = re.compile(r'(.*?)_((?:\d+?)|(?:NA))_(?:(.{11})_)?(.*)\.'
                         r'(jpg|webp|flv|mp4|part|info\.json|description|webm|..\.srt|..\.vtt)')


def upsert_video(session: Session, video_path: pathlib.Path, channel: Channel = None, idempotency: str = None,
                 skip_captions=False, id_: str = None) -> Video:
    """
    Insert a video into the DB.  Also, find any meta-files near the video file and store them on the video row.

    If id_ is provided, update that entry.
    """
    if not video_path.is_absolute():
        raise ValueError(f'Video path is not absolute: {video_path}')
    poster_path, description_path, caption_path, info_json_path = find_meta_files(video_path)

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
    url = None
    if info_json_path:
        try:
            with info_json_path.open('rt') as fh:
                json_contents = json.load(fh)
                duration = json_contents.get('duration')
                url = json_contents.get('webpage_url')
                # Trust the info_json title before the video filename.
                title = json_contents.get('title', title)
        except json.decoder.JSONDecodeError:
            logger.warning(f'Failed to load JSON file to get duration: {info_json_path}')

    size = video_path.stat().st_size
    title = html.unescape(title) if title else None

    video_dict = dict(
        caption_path=str(caption_path) if caption_path else None,
        channel_id=channel.id if channel else None,
        description_path=str(description_path) if description_path else None,
        duration=duration,
        ext=ext,
        idempotency=idempotency,
        info_json_path=str(info_json_path) if info_json_path else None,
        poster_path=str(poster_path) if poster_path else None,
        size=size,
        source_id=source_id,
        title=title,
        upload_date=upload_date,
        url=url,
        video_path=str(video_path),
    )

    if id_:
        video = session.query(Video).filter_by(id=id_).one()
        for key, value in video_dict.items():
            setattr(video, key, value)
    else:
        video = Video(**video_dict)

    session.add(video)
    session.flush()

    if skip_captions is False and caption_path:
        # Process captions only when requested
        get_video_captions(video)

    return video


def find_meta_files(path: pathlib.Path) -> Tuple[pathlib.Path, pathlib.Path, pathlib.Path, pathlib.Path]:
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
                yield meta_path
                break
        else:
            yield None
