import asyncio
import random
from datetime import timedelta
from typing import Tuple, Optional, List

import yt_dlp
from sqlalchemy import or_
from sqlalchemy.orm import Session

from modules.videos.models import Video, Channel
from wrolpi import fts
from wrolpi.common import logger, limit_concurrent, wrol_mode_check
from wrolpi.dates import now
from wrolpi.db import get_db_session, get_db_curs
from wrolpi.downloader import download_manager
from wrolpi.files.lib import handle_file_group_search_results, cached_search_total, \
    search_filter_cache_key, count_file_groups
from wrolpi.files.models import FileGroup
from wrolpi.tags import tag_append_sub_select_where
from wrolpi.vars import VIDEO_COMMENTS_FETCH_COUNT, YTDLP_CACHE_DIR
from ..cookies import cookies_unlocked, cookies_for_download
from ..lib import get_yt_dlp_http_headers, get_yt_dlp_sleep_opts

logger.getChild(__name__)


def get_video_for_app(file_group_id: int, skip_viewed: bool = False) -> Tuple[dict, Optional[dict], Optional[dict]]:
    """
    Get a Video by its FileGroup ID, with its prev/next videos.  Mark the Video as viewed.
    """
    with get_db_session(commit=True) as session:
        video = Video.find_by_file_group_id(session, file_group_id)
        if not skip_viewed:
            video.file_group.set_viewed()
        previous_video, next_video = video.get_surrounding_videos()

        video = video.__json__()
        previous_video = previous_video.__json__() if previous_video and previous_video.file_group else None
        next_video = next_video.__json__() if next_video and next_video.file_group else None

    return video, previous_video, next_video


def get_video(file_group_id: int) -> Video:
    """
    Get a Video by its FileGroup ID.
    """
    with get_db_session() as session:
        video = Video.find_by_file_group_id(session, file_group_id)
        return video


@wrol_mode_check
def update_video(file_group_id: int, title: str = None, description: str = None) -> Video:
    """Edit a Video's details.  The files are the source of truth, so the change is written to the
    Video's .info.json (created if missing) and the Video is validated again from it.  Only the
    fields given (not None) are changed; an empty description clears it.

    A later re-download of the Video's metadata will overwrite the info json, and this edit with
    it.

    @raise UnknownVideo: if the Video can not be found
    @raise ValidationError: when nothing is given, or the title is empty
    """
    from wrolpi.errors import ValidationError
    if title is None and description is None:
        raise ValidationError('Nothing to change')
    if title is not None:
        title = title.strip()
        if not title:
            raise ValidationError('Video title cannot be empty')

    with get_db_session(commit=True) as session:
        video = Video.find_by_file_group_id(session, file_group_id)
        info_json = video.get_info_json() or dict()
        if title is not None:
            # `extract_video_info_json` prefers fulltitle over title; keep the two in agreement.
            info_json['title'] = title
            info_json['fulltitle'] = title
        if description is not None:
            info_json['description'] = description
        # Keep the file as it was, other than the edited fields.
        video.replace_info_json(info_json, clean=False)
        # Re-derive the title (and search text) from the file just written.
        video.validate(session)
        video.flush()
        return video


VIDEO_ORDERS = {
    # fg.id (the rowid) is the pagination tiebreaker: it is present in every index, so these
    # orders stay index-only.  LOWER(fg.primary_path) forced SQLite to read every (large) row.
    # Sometimes we don't have a published_datetime.  This is equivalent to COALESCE(fg.published_datetime, fg.download_datetime)
    'published_datetime': 'fg.effective_datetime ASC, fg.id ASC',
    '-published_datetime': 'fg.effective_datetime DESC NULLS LAST, fg.id ASC',
    'rank': '2 DESC, fg.id DESC',
    '-rank': '2 ASC, fg.id ASC',
    'size': 'fg.size ASC, fg.id ASC',
    '-size': 'fg.size DESC, fg.id DESC',
    'length': 'fg.length ASC, fg.id ASC',
    '-length': 'fg.length DESC, fg.id DESC',
    'size_to_duration': 'CASE WHEN fg.length > 0 THEN CAST(fg.size AS REAL) / fg.length ELSE fg.size END ASC, fg.id ASC',
    '-size_to_duration': 'CASE WHEN fg.length > 0 THEN CAST(fg.size AS REAL) / fg.length ELSE fg.size END DESC, fg.id DESC',
    'viewed': 'fg.viewed ASC',
    '-viewed': 'fg.viewed DESC',
    'view_count': 'v.view_count ASC',
    '-view_count': 'v.view_count DESC',
    'download_datetime': 'fg.download_datetime ASC, fg.id ASC',
    '-download_datetime': 'fg.download_datetime DESC NULLS LAST, fg.id ASC',
}
NO_NULL_ORDERS = {
    'viewed': 'fg.viewed IS NOT NULL',
    '-viewed': 'fg.viewed IS NOT NULL',
    'length': 'fg.length IS NOT NULL',
    '-length': 'fg.length IS NOT NULL',
    'size': 'fg.size IS NOT NULL',
    '-size': 'fg.size IS NOT NULL',
    'size_to_duration': 'fg.size IS NOT NULL AND fg.length IS NOT NULL',
    '-size_to_duration': 'fg.size IS NOT NULL AND fg.length IS NOT NULL',
    'view_count': 'v.view_count IS NOT NULL',
    '-view_count': 'v.view_count IS NOT NULL',
}
JOIN_ORDERS = ('view_count', '-view_count')
DEFAULT_VIDEO_ORDER = 'rank'
VIDEO_QUERY_LIMIT = 24

# Orders the unfiltered Videos page can serve straight from the (mimetype, effective_datetime) index.
INDEXED_DATE_ORDERS = ('published_datetime', '-published_datetime')
VIDEO_MIMETYPE_PREFIXES = ('video/', 'audio/')


def _video_mimetypes() -> List[str]:
    """Every distinct video/* and audio/* mimetype in the library (a handful; served by the mimetype index)."""
    mimetypes = []
    with get_db_curs() as curs:
        for prefix in VIDEO_MIMETYPE_PREFIXES:
            # '0' is the character after '/', so this is the half-open range of the prefix.
            curs.execute('SELECT DISTINCT mimetype FROM file_group WHERE mimetype >= ? AND mimetype < ?',
                         (prefix, prefix[:-1] + '0'))
            mimetypes.extend(i[0] for i in curs.fetchall())
    return mimetypes


def _count_videos() -> int:
    ranges = ' OR '.join(f'(mimetype >= :p{i} AND mimetype < :e{i})' for i in range(len(VIDEO_MIMETYPE_PREFIXES)))
    params = dict()
    for i, prefix in enumerate(VIDEO_MIMETYPE_PREFIXES):
        params[f'p{i}'], params[f'e{i}'] = prefix, prefix[:-1] + '0'
    with get_db_curs() as curs:
        curs.execute(f'SELECT COUNT(*) FROM file_group WHERE {ranges}', params)
        return curs.fetchone()[0]


def _search_videos_by_date(order: str, limit: int, offset: int) -> Tuple[List[dict], int]:
    """The unfiltered Videos page, ordered by date, without visiting every video.

    The generic query (`mimetype LIKE 'video/%' OR ...`) plus a windowed COUNT used to visit every
    video before LIMIT.  Here each exact mimetype is a covering-index seek on
    (mimetype, effective_datetime) that reads only `limit + offset` entries; those few rows are
    then merged.  Results must be identical to the generic query's (same ORDER BY, including the
    id tiebreaker and NULL placement).  The total is a separate, cached count."""
    order_by = VIDEO_ORDERS[order]
    mimetypes = _video_mimetypes()
    if not mimetypes:
        return [], 0

    n = limit + offset
    params = {f'mt{i}': mimetype for i, mimetype in enumerate(mimetypes)}
    params['offset'] = offset
    members = '\n UNION ALL\n'.join(
        f'SELECT * FROM (SELECT fg.id, fg.effective_datetime FROM file_group fg'
        f' WHERE fg.mimetype = :mt{i} ORDER BY {order_by} LIMIT {n})'
        for i in range(len(mimetypes))
    )
    stmt = f'''
        SELECT fg.id
        FROM ({members}) fg
        ORDER BY {order_by}
        LIMIT {limit} OFFSET :offset
    '''.strip()
    logger.debug(f'{stmt} {params}')

    total = cached_search_total(search_filter_cache_key('videos'), _count_videos)
    return handle_file_group_search_results(stmt, params, total=total)


def search_videos(
        search_str: str = None,
        offset: int = None,
        limit: int = VIDEO_QUERY_LIMIT,
        channel_id: int = None,
        order: str = None,
        tag_names: List[str] = None,
        headline: bool = False,
        censored: bool = False,
        deep: bool = False,
) -> Tuple[List[dict], int]:
    tag_names = tag_names or []
    # Search videos and audio-only files.
    wheres = ["(fg.mimetype LIKE 'video/%' OR fg.mimetype LIKE 'audio/%')"]
    if censored:
        # Only return videos which are no longer available for download.
        wheres.append('fg.censored = TRUE')
    joins = list()
    join_video = False

    # Explicit JSON nulls bypass the schema defaults; SQLite rejects LIMIT/OFFSET NULL.
    limit = int(limit) if limit else 20
    offset = int(offset) if offset else 0
    if not search_str and not tag_names and not channel_id and not censored and order in INDEXED_DATE_ORDERS:
        # The Videos page with no filters, in date order.
        return _search_videos_by_date(order, limit, offset)

    params = dict(search_str=search_str, offset=offset)
    if channel_id:
        wheres.append('v.channel_id = :channel_id')
        joins.append('LEFT JOIN channel c ON c.id = v.channel_id')
        join_video = True
        params['channel_id'] = channel_id

    # `deep` searches d_text (captions) as well; the default abc search is much smaller and faster.
    # Rank/snippets come from a subquery so they stay valid if a caller adds window functions.
    fts_search = fts.file_group_search_join(search_str, deep=deep, headlines=bool(headline)) \
        if search_str else None
    if fts_search:
        select_columns = f'fg.id, {fts_search.rank_select}'
        joins.append(fts_search.join)
        params.update(fts_search.params)
    else:
        select_columns = 'fg.id'

    wheres, params = tag_append_sub_select_where(wheres, params, tag_names)

    if fts_search and headline:
        # The title headline is computed in Python by `handle_file_group_search_results`.
        headline_selects = ', fts.b_headline, fts.c_headline, fts.d_headline'
    else:
        headline_selects = ''

    # Convert the user-friendly order by into a real order by, restrict what can be interpolated by using the
    # whitelist.
    order_by = VIDEO_ORDERS[DEFAULT_VIDEO_ORDER]
    null_filter = None
    if order:
        try:
            order_by = VIDEO_ORDERS[order]
        except KeyError:
            raise
        if order in NO_NULL_ORDERS:
            null_filter = NO_NULL_ORDERS[order]
            wheres.append(null_filter)
        if order in JOIN_ORDERS:
            join_video = True

    effective_order = order or DEFAULT_VIDEO_ORDER
    if not fts_search and effective_order in ('rank', '-rank'):
        # Rank without a search used to ORDER BY the windowed total (a constant).  Equivalent: id.
        order_by = 'fg.id ASC' if effective_order == '-rank' else 'fg.id DESC'

    if join_video:
        joins.insert(0, 'LEFT JOIN video v on v.file_group_id = fg.id')

    where = ('WHERE\n' + '\n AND '.join(wheres)) if wheres else ''
    join = '\n'.join(joins)
    stmt = f'''
        SELECT
            {select_columns}
            {headline_selects}
        FROM file_group fg
        {join}
        {where}
        ORDER BY {order_by}
        LIMIT {int(limit)} OFFSET :offset
    '''.strip()
    logger.debug(f'{stmt} {params}')

    unfiltered = (not search_str and not tag_names and not channel_id and not censored
                  and not null_filter)
    if unfiltered:
        total = cached_search_total(search_filter_cache_key('videos'), _count_videos)
    else:
        if fts_search:
            fts_count = fts.file_group_search(search_str, deep=deep)
            count_joins = [j for j in joins if 'file_group_fts' not in j]
            if fts_count:
                count_joins.append(fts_count.join)
            count_wheres = [w for w in wheres]
            if fts_count:
                count_wheres.append(fts_count.where)
            count_join = '\n'.join(count_joins)
            count_where = ('WHERE\n' + '\n AND '.join(count_wheres)) if count_wheres else ''
            count_stmt = f'SELECT COUNT(*) AS total FROM file_group fg {count_join} {count_where}'
            count_params = dict(params)
            if fts_count:
                count_params.update(fts_count.params)
        else:
            count_stmt = f'SELECT COUNT(*) AS total FROM file_group fg {join} {where}'
            count_params = params
        cache_key = search_filter_cache_key(
            'videos', search_str=search_str, channel_id=channel_id, tag_names=tag_names,
            censored=censored, deep=deep, null_filter=null_filter,
        )
        total = cached_search_total(cache_key, lambda: count_file_groups(count_stmt, count_params))

    results, total = handle_file_group_search_results(stmt, params, total=total)
    return results, total


def download_video_info_json(url: str) -> dict:
    """Download video info JSON, using encrypted cookies for authentication if available."""
    ydl_opts = dict(
        getcomments=True,
        skip_download=True,
        extractor_args={'youtube': {'max_comments': ['all', '20', 'all', '10'], 'comment_sort': ['top']}},
        cachedir=YTDLP_CACHE_DIR,
        **get_yt_dlp_sleep_opts(),
    )

    ydl_logger = logger.getChild('youtube-dl')

    if cookies_unlocked():
        logger.info(f'Using encrypted cookies for video info: {url}')
        with cookies_for_download() as cookies_path:
            ydl_opts['cookiefile'] = str(cookies_path)
            http_headers = get_yt_dlp_http_headers()
            if http_headers:
                ydl_opts['http_headers'] = http_headers
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.params['logger'] = ydl_logger
                info = ydl.extract_info(url, download=False)
                ydl.sanitize_info(info)
                return info

    logger.info(f'No cookies available for video info: {url}')

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.params['logger'] = ydl_logger
        info = ydl.extract_info(url, download=False)
        ydl.sanitize_info(info)
        return info


@limit_concurrent(1)
@wrol_mode_check
async def get_missing_videos_comments(limit: int = VIDEO_COMMENTS_FETCH_COUNT):
    """
    Fetches Video info json for videos without comments, if comments are found then the info json file is replaced.
    Uses encrypted cookies for authentication if available.
    """
    one_month_ago = now() - timedelta(days=30)

    # Get any videos over a month old that do not have comments.
    with get_db_session() as session:
        videos = session.query(Video).filter(
            # Have yet to get comments.
            Video.have_comments != True,
            Video.comments_failed != True,
            # Needs to be downloadable.
            FileGroup.url != None,  # noqa
            FileGroup.censored != True,
            # We want old videos (time for comments to accumulate), or those which we don't know the published date.
            or_(
                one_month_ago > FileGroup.published_datetime,
                FileGroup.published_datetime == None,
            ),
            # Do not download a Videos with a Channel and Channel.download_missing_data is False.
            or_(
                Channel.download_missing_data == True,
                Channel.id == None,
            )
        ).join(FileGroup) \
            .outerjoin(Channel) \
            .order_by(FileGroup.published_datetime.nullsfirst()) \
            .limit(limit)
        video_urls = [i.file_group.url for i in videos]

    logger.info(f'Found {len(video_urls)} videos missing comments')

    def add_video_to_skip_list(video_url: str, censored: bool = False):
        """Do not attempt to get comments of the provided Video again."""
        with get_db_session(commit=True) as session_:
            for video_, fg in session_.query(Video, FileGroup).join(FileGroup).filter_by(url=video_url).all():
                video_.comments_failed = True
                fg.censored = censored
        download_manager.add_to_skip_list(video_url)
        logger.debug(f'add_video_to_skip_list: {video_url=} {censored=}')

    for url in video_urls:
        # Sleep to catch cancel.
        await asyncio.sleep(0)

        if download_manager.is_skipped(url):
            # This video is skipped, do not try to get comments again.
            add_video_to_skip_list(url)

        if download_manager.is_disabled or download_manager.is_stopped:
            logger.info('Downloads disabled, stop getting comments...')
            return

        with get_db_session(commit=True) as session:
            have_comments = False
            for video in session.query(Video).join(FileGroup).filter_by(url=url).all():
                if (comments := video.get_comments()) and len(comments) >= 5:
                    # We already have enough comments.  DB may have been wiped, we don't want to fetch comments again.
                    logger.info(f'Already have comments for Video: {url=}')
                    have_comments = video.have_comments = True

            if have_comments:
                download_manager.add_to_skip_list(url)
                continue

        logger.info(f'Getting comments for: {url}')

        try:
            # Get info json about the video.
            info = download_video_info_json(url)

            if not info or not isinstance(info.get('comments'), list):
                logger.error(f'Unable to get comments for video: {url=}')
                add_video_to_skip_list(url)
                continue
        except Exception as e:
            if 'no longer available' in str(e):
                logger.error(f'Giving up on downloading comments because video does not exist: {url=}', exc_info=e)
                add_video_to_skip_list(url, censored=True)
            elif 'Comments are turned off' in str(e):
                logger.error(f'Giving up on downloading comments because comments are disabled: {url=}', exc_info=e)
                add_video_to_skip_list(url)
            elif 'Private video' in str(e):
                logger.error(f'Giving up on downloading comments because video is private: {url=}', exc_info=e)
                add_video_to_skip_list(url, censored=True)
            elif 'Video unavailable' in str(e):
                logger.error(f'Giving up on downloading comments because video is unavailable: {url=}', exc_info=e)
                add_video_to_skip_list(url, censored=True)
            elif 'video has been removed' in str(e):
                logger.error(f'Giving up on downloading comments because video is removed: {url=}', exc_info=e)
                add_video_to_skip_list(url, censored=True)
            elif ' members' in str(e):
                logger.error(f'Giving up on downloading comments because video is members-only: {url=}', exc_info=e)
                add_video_to_skip_list(url, censored=True)
            elif 'rumble.com' in url and "'bool' object has no attribute 'get'" in str(e):
                logger.error(f'Rumble error in yt-dlp', exc_info=e)
                add_video_to_skip_list(url, censored=False)
            elif 'not a valid URL' in str(e):
                logger.error(f'URL is not valid: {url=}', exc_info=e)
                add_video_to_skip_list(url, censored=True)
            elif ' Sign in ' in str(e):
                logger.error(f'Video requires sign-in: {url=}', exc_info=e)
                add_video_to_skip_list(url, censored=True)
            else:
                logger.error(f'Got error when attempting to download video comments: {url=}', exc_info=e)
            continue

        logger.info(f'Got {len(info["comments"])} comments for Video: {url=}')

        with get_db_session(commit=True) as session:
            videos = list(session.query(Video).join(FileGroup).filter_by(url=url).all())
            for video in videos:
                if video.video_path.is_file():
                    video.replace_info_json(info)
                    video.have_comments = True
                    video.comments_failed = False
                else:
                    logger.error(f'Attempting to replace comments for non-existent video!  {video}')
                    if len(videos) == 1:
                        download_manager.add_to_skip_list(url)
                    video.comments_failed = True

        # Sleep a random amount of time, so we don't spam.
        await asyncio.sleep(random.randint(2, 20))
