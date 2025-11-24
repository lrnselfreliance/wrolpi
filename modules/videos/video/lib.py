import asyncio
import random
from datetime import timedelta
from typing import Tuple, Optional, List

import yt_dlp
from sqlalchemy import or_
from sqlalchemy.orm import Session

from modules.videos.models import Video, Channel
from wrolpi.common import logger, limit_concurrent, wrol_mode_check
from wrolpi.dates import now
from wrolpi.db import get_db_session, optional_session
from wrolpi.downloader import download_manager
from wrolpi.files.lib import handle_file_group_search_results
from wrolpi.files.models import FileGroup
from wrolpi.tags import tag_append_sub_select_where
from wrolpi.vars import VIDEO_COMMENTS_FETCH_COUNT, YTDLP_CACHE_DIR
from ..errors import UnknownVideo

logger.getChild(__name__)


def get_video_for_app(video_id: int) -> Tuple[dict, Optional[dict], Optional[dict]]:
    """
    Get a Video, with it's prev/next videos.  Mark the Video as viewed.
    """
    with get_db_session(commit=True) as session:
        video = Video.find_by_id(video_id, session=session)
        video.file_group.set_viewed()
        previous_video, next_video = video.get_surrounding_videos()

        video = video.__json__()
        previous_video = previous_video.__json__() if previous_video and previous_video.file_group else None
        next_video = next_video.__json__() if next_video and next_video.file_group else None

    return video, previous_video, next_video


def get_video(video_id: int) -> Video:
    """
    Get a Video, with it's prev/next videos.  Mark the Video as viewed.
    """
    with get_db_session() as session:
        video = Video.find_by_id(video_id, session=session)
        return video


VIDEO_ORDERS = {
    # Sometimes we don't have a published_datetime.  This is equivalent to COALESCE(fg.published_datetime, fg.download_datetime)
    'published_datetime': 'fg.effective_datetime ASC, LOWER(fg.primary_path) ASC',
    '-published_datetime': 'fg.effective_datetime DESC NULLS LAST, LOWER(fg.primary_path) ASC',
    'rank': '2 DESC, LOWER(fg.primary_path) DESC',
    '-rank': '2 ASC, LOWER(fg.primary_path) ASC',
    'size': 'fg.size ASC, LOWER(fg.primary_path) ASC',
    '-size': 'fg.size DESC, LOWER(fg.primary_path) DESC',
    'length': 'fg.length ASC, LOWER(fg.primary_path) ASC',
    '-length': 'fg.length DESC, LOWER(fg.primary_path) DESC',
    'size_to_duration': 'CASE WHEN fg.length > 0 THEN fg.size::float / fg.length ELSE fg.size END ASC, LOWER(fg.primary_path) ASC',
    '-size_to_duration': 'CASE WHEN fg.length > 0 THEN fg.size::float / fg.length ELSE fg.size END DESC, LOWER(fg.primary_path) DESC',
    'viewed': 'fg.viewed ASC',
    '-viewed': 'fg.viewed DESC',
    'view_count': 'v.view_count ASC',
    '-view_count': 'v.view_count DESC',
    'download_datetime': 'fg.download_datetime ASC, LOWER(fg.primary_path) ASC',
    '-download_datetime': 'fg.download_datetime DESC NULLS LAST, LOWER(fg.primary_path) ASC',
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


def search_videos(
        search_str: str = None,
        offset: int = None,
        limit: int = VIDEO_QUERY_LIMIT,
        channel_id: int = None,
        order: str = None,
        tag_names: List[str] = None,
        headline: bool = False,
) -> Tuple[List[dict], int]:
    tag_names = tag_names or []
    # Only search videos.
    wheres = ["fg.mimetype LIKE 'video/%%'"]
    joins = list()
    join_video = False

    params = dict(search_str=search_str, offset=offset or 0)
    if channel_id:
        wheres.append('v.channel_id = %(channel_id)s')
        joins.append('LEFT JOIN channel c ON c.id = v.channel_id')
        join_video = True
        params['channel_id'] = channel_id

    if search_str:
        # A search_str was provided by the user, modify the query to filter by it.
        select_columns = 'fg.id, ts_rank(fg.textsearch, websearch_to_tsquery(%(search_str)s)), COUNT(*) OVER() AS total'
        wheres.append('fg.textsearch @@ websearch_to_tsquery(%(search_str)s)')
        params['search_str'] = search_str
    else:
        # No search_str provided.  Get id and total only.
        select_columns = 'fg.id, COUNT(*) OVER() AS total'

    wheres, params = tag_append_sub_select_where(wheres, params, tag_names)

    if search_str and headline:
        headline = ''',
           ts_headline(fg.title, websearch_to_tsquery(%(search_str)s)) AS "title_headline",
           ts_headline(fg.b_text, websearch_to_tsquery(%(search_str)s)) AS "b_headline",
           ts_headline(fg.c_text, websearch_to_tsquery(%(search_str)s)) AS "c_headline",
           ts_headline(fg.d_text, websearch_to_tsquery(%(search_str)s)) AS "d_headline"'''
    else:
        headline = ''

    # Convert the user-friendly order by into a real order by, restrict what can be interpolated by using the
    # whitelist.
    order_by = VIDEO_ORDERS[DEFAULT_VIDEO_ORDER]
    if order:
        try:
            order_by = VIDEO_ORDERS[order]
        except KeyError:
            raise
        if order in NO_NULL_ORDERS:
            wheres.append(NO_NULL_ORDERS[order])
        if order in JOIN_ORDERS:
            join_video = True

    if join_video:
        joins.insert(0, 'LEFT JOIN video v on v.file_group_id = fg.id')

    wheres = '\n AND '.join(wheres)
    where = f'WHERE\n{wheres}' if wheres else ''
    join = '\n'.join(joins)
    stmt = f'''
        SELECT
            {select_columns}
            {headline}
        FROM file_group fg
        {join}
        {where}
        ORDER BY {order_by}
        OFFSET %(offset)s LIMIT {int(limit)}
    '''.strip()
    logger.debug(stmt, params)

    results, total = handle_file_group_search_results(stmt, params)
    return results, total


@optional_session
def delete_videos(*video_ids: int, session: Session = None):
    videos = list(session.query(Video).filter(Video.id.in_(video_ids)))
    if not videos:
        raise UnknownVideo('Could not find videos to delete')

    logger.warning(f'Deleting {len(videos)} videos')
    # Get all URLs, skip them once (so config isn't saved multiple times).
    urls = list(filter(None, [i.file_group.url for i in videos]))
    download_manager.add_to_skip_list(*urls)
    for video in videos:
        video.delete()
    session.commit()


def download_video_info_json(url: str) -> dict:
    ydl_opts = dict(
        getcomments=True,
        skip_download=True,
        extractor_args={'youtube': {'max_comments': ['all', '20', 'all', '10'], 'comment_sort': ['top']}},
        cachedir=YTDLP_CACHE_DIR,
    )

    ydl_logger = logger.getChild('youtube-dl')

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
