import asyncio
import random
from datetime import timedelta
from typing import Tuple, Optional, List, Dict

import yt_dlp
from sqlalchemy import or_
from sqlalchemy.orm import Session

from modules.videos.models import Video
from wrolpi.common import run_after, logger, limit_concurrent, wrol_mode_check
from wrolpi.dates import now
from wrolpi.db import get_db_session, optional_session
from wrolpi.downloader import download_manager
from wrolpi.files.lib import handle_file_group_search_results
from wrolpi.files.models import FileGroup
from wrolpi.tags import tag_append_sub_select_where
from wrolpi.vars import VIDEO_COMMENTS_FETCH_COUNT
from ..errors import UnknownVideo
from ..lib import save_channels_config

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


VIDEO_ORDERS = {
    'published_datetime': 'COALESCE(fg.published_datetime, fg.download_datetime) ASC, LOWER(fg.primary_path) ASC',
    '-published_datetime': 'COALESCE(fg.published_datetime, fg.download_datetime) DESC NULLS LAST,'
                           ' LOWER(fg.primary_path) ASC',
    'rank': '2 DESC, LOWER(fg.primary_path) DESC',
    '-rank': '2 ASC, LOWER(fg.primary_path) ASC',
    'size': 'fg.size ASC, LOWER(fg.primary_path) ASC',
    '-size': 'fg.size DESC, LOWER(fg.primary_path) DESC',
    'length': 'fg.length ASC, LOWER(fg.primary_path) ASC',
    '-length': 'fg.length DESC, LOWER(fg.primary_path) DESC',
    'viewed': 'fg.viewed ASC',
    '-viewed': 'fg.viewed DESC',
    'view_count': 'v.view_count ASC',
    '-view_count': 'v.view_count DESC',
}
NO_NULL_ORDERS = {
    'viewed': 'fg.viewed IS NOT NULL',
    '-viewed': 'fg.viewed IS NOT NULL',
    'length': 'fg.length IS NOT NULL',
    '-length': 'fg.length IS NOT NULL',
    'size': 'fg.size IS NOT NULL',
    '-size': 'fg.size IS NOT NULL',
    'view_count': 'v.view_count IS NOT NULL',
    '-view_count': 'v.view_count IS NOT NULL',
}
JOIN_ORDERS = ('published_datetime', '-published_datetime', 'viewed', '-viewed', 'view_count', '-view_count',
               'length', '-length')
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

    params = dict(search_str=search_str, offset=offset)
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

    wheres, params = tag_append_sub_select_where(tag_names, wheres, params)

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


@run_after(save_channels_config)
def tag_video(video_id: int, tag_name: str) -> Dict:
    """Tag a video"""
    with get_db_session(commit=True):
        video = Video.find_by_id(video_id)
        video.add_tag(tag_name)
        video_dict = video.dict()
    return video_dict


@optional_session
def delete_videos(*video_ids: int, session: Session = None):
    videos = list(session.query(Video).filter(Video.id.in_(video_ids)))
    if not videos:
        raise UnknownVideo('Could not find videos to delete')

    logger.warning(f'Deleting {len(videos)} videos')
    for video in videos:
        video.delete()
    session.commit()


def download_video_info_json(url: str) -> dict:
    ydl_opts = dict(
        getcomments=True,
        skip_download=True,
        extractor_args={'youtube': {'max_comments': ['all', '20', 'all', '10'], 'comment_sort': ['top']}},
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
            Video.have_comments == False,
            Video.comments_failed == False,
            # Need a URL to try to get comments.
            FileGroup.url != None,  # noqa
            # We want old videos (time for comments to accumulate), or those which we don't know the published date.
            or_(
                one_month_ago > FileGroup.published_datetime,
                FileGroup.published_datetime == None,
            ),
        ).join(FileGroup) \
            .order_by(FileGroup.published_datetime.nullsfirst()) \
            .limit(limit)
        video_urls = [i.file_group.url for i in videos]

    logger.info(f'Found {len(video_urls)} videos missing comments')

    def add_video_to_skip_list(video_url: str):
        """Do not attempt to get comments of the provided Video again."""
        with get_db_session(commit=True) as session_:
            for video_ in session_.query(Video).join(FileGroup).filter_by(url=video_url).all():
                video_.comments_failed = True
        download_manager.add_to_skip_list(video_url)

    for url in video_urls:
        # Sleep to catch cancel.
        await asyncio.sleep(0)

        if download_manager.is_skipped(url):
            # This video is skipped, do not try to get comments again.
            add_video_to_skip_list(url)

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

        tries = 5
        info = None
        while tries > 0:
            try:
                tries -= 1
                # Get info json about the video.  Retry until we have a list of comments.
                info = download_video_info_json(url)
                if info and isinstance(info.get('comments'), list):
                    break
            except Exception as e:
                if 'no longer available' in str(e):
                    logger.error(f'Giving up on downloading comments because video does not exist: {url=}', exc_info=e)
                    break
                if 'Comments are turned off' in str(e):
                    logger.error(f'Giving up on downloading comments because comments are disabled: {url=}', exc_info=e)
                    break
                if 'Private video' in str(e):
                    logger.error(f'Giving up on downloading comments because video is private: {url=}', exc_info=e)
                    break
                if 'Video unavailable' in str(e):
                    logger.error(f'Giving up on downloading comments because video is unavailable: {url=}', exc_info=e)
                    break
                logger.error(f'Got error when attempting to download video comments: {url=}', exc_info=e)
                await asyncio.sleep(random.randint(1, 5))

        if not info or not isinstance(info.get('comments'), list):
            logger.error(f'Never got comments for video: {url=}')
            add_video_to_skip_list(url)
            continue

        logger.debug(f'Got {len(info["comments"])} comments for Video: {url=}')

        with get_db_session(commit=True) as session:
            for video in session.query(Video).join(FileGroup).filter_by(url=url).all():
                video.replace_info_json(info)
                video.have_comments = True

        # Sleep a random amount of time, so we don't spam.
        await asyncio.sleep(random.randint(2, 20))
