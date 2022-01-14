import html
import pathlib
import re
from collections import defaultdict
from typing import Tuple, Optional
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
        curs.execute('SELECT id, generate_posters FROM channel')
        channel_generate_posters = {i['id']: i['generate_posters'] for i in curs.fetchall()}

    logger.info(f'Validating {len(video_ids)} videos.')
    for chunk in chunks(video_ids, 20):
        with get_db_session(commit=True) as session:
            videos = session.query(Video).filter(Video.id.in_(chunk)).all()
            for video in videos:
                try:
                    channel_generate_poster = channel_generate_posters.get(video.channel_id)
                    validate_video(video, channel_generate_poster)
                    # All data about the Video has been found, we should not attempt to validate it again.
                    video.validated = True
                except Exception as e:
                    # This video failed to validate, continue validation for the rest of the videos.
                    logger.warning(f'Failed to validate {video=}', exc_info=e)


def validate_video(video: Video, channel_generate_poster: bool):
    """
    Validate a single video.  A Video is validated when we have attempted to find its: title, duration,
    view_count, url, caption, size.  A Video is also valid when it has a JPEG poster, if any.  If no poster can be
    found, it will be generated from the video file.
    """
    if not video.title or not video.duration or not video.view_count or not video.url:
        # These properties can be found in the info json.
        title, duration, view_count, url = process_video_info_json(video)
        video.title = title
        video.duration = duration
        video.url = url
        # View count will probably be overwritten by more recent data when this Video's Channel is
        # updated.
        video.view_count = video.view_count or view_count

    video_path = video.video_path.path if isinstance(video.video_path, MediaPath) else video.video_path

    if not video.title or not video.upload_date or not video.source_id:
        # Video is missing things that can be extracted from the video file name.
        # These are the least trusted, so anything already on the video should be trusted.
        _, upload_date, source_id, title = parse_video_file_name(video_path)
        video.title = video.title or html.unescape(title)
        video.upload_date = video.upload_date or upload_date
        video.source_id = video.source_id or source_id
    if not video.duration:
        # Video duration was not in the info json, use ffprobe.
        video.duration = get_video_duration(video_path)
    if not video.caption and video.caption_path:
        video.caption = get_video_captions(video)
    if not video.size:
        video.size = video_path.stat().st_size
    if not video.poster_path:
        # Video poster is not found, lets check near the video file.
        for ext in ('.jpg', '.jpeg', '.webp', '.png'):
            if (poster_path := video_path.with_suffix(ext)).is_file():
                video.poster_path = poster_path
                break
    if channel_generate_poster:
        # Try to convert/generate, but keep the old poster if those fail.
        video.poster_path = convert_or_generate_poster(video) or video.poster_path


def convert_or_generate_poster(video: Video) -> Optional[pathlib.Path]:
    """
    If a Video has a poster, but the poster is invalid, convert it.  If a Video has no poster, generate one from the
    video file.

    Returns None if the poster was not converted, and not generated.
    """
    video_path = video.video_path.path
    # Modification/generation of poster is enabled for this channel.
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
                logger.info(f'Converted invalid poster {old} to {new}')
                return new
            except Exception as e:
                logger.error(f'Failed to convert invalid poster {old} to {new}', exc_info=e)
                return

    if not video.poster_path:
        # Video poster was not discovered, or converted.  Let's generate it.
        try:
            poster_path = generate_video_poster(video_path)
            logger.debug(f'Generated poster for {video}')
            return poster_path
        except Exception as e:
            logger.error(f'Failed to generate poster for {video}', exc_info=e)


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

    logger.info('Refresh of video files complete')


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


NAME_PARSER = re.compile(r'(.*?)_((?:\d+?)|(?:NA))_(?:(.+?)_)?(.*)\.'
                         r'(jpg|webp|flv|mp4|part|info\.json|description|webm|..\.srt|..\.vtt)')


def parse_video_file_name(video_path: pathlib.Path) -> \
        Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    A Video's file name can have data in it, this attempts to extract what may be there.

    Example: {channel_name}_{upload_date}_{source_id}_title{ext}
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
    title = pathlib.Path(video_path).stem.strip()
    return None, None, None, title


def upsert_video(session: Session, video_path: pathlib.Path, channel: Channel = None, idempotency: str = None,
                 id_: str = None) -> Video:
    """
    Insert a video into the DB.  Also, find any meta-files near the video file and store them on the video row.

    If id_ is provided, update that entry.
    """
    if not video_path.is_absolute():
        raise ValueError(f'Video path is not absolute: {video_path}')

    # This function can update or insert a Video.
    video = session.query(Video).filter_by(id=id_).one() if id_ else Video()

    # Set the file values, all other things can be found using these files.
    poster_path, description_path, caption_path, info_json_path = find_meta_files(video_path)
    video.caption_path = caption_path
    video.description_path = description_path
    video.info_json_path = info_json_path
    video.poster_path = poster_path
    video.video_path = video_path

    if channel and not str(video_path).startswith(str(channel.directory.path)):
        raise ValueError(f'Video path is not within its channel {video_path=} not in {channel.directory=}')

    video.channel = channel
    video.idempotency = idempotency

    try:
        # Fill in any missing data.  Generate poster if enabled and necessary.
        validate_video(video, channel.generate_posters if channel else False)
        # All data about the Video has been found, we should not attempt to validate it again.
        video.validated = True
    except Exception:
        # Could not validate, this could be an issue with a file.  This should not prevent the video from being
        # inserted.
        pass

    session.add(video)
    session.flush()

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
