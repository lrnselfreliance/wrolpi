from datetime import datetime
from typing import Tuple, Optional, List

from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import NoResultFound

from wrolpi.common import run_after, logger
from wrolpi.db import get_db_session, optional_session
from wrolpi.errors import UnknownVideo
from wrolpi.files.lib import handle_search_results
from ..lib import save_channels_config
from ..models import Video

logger.getChild(__name__)


def get_video(session: Session, video_id: int) -> Video:
    try:
        video = session.query(Video).filter_by(id=video_id).one()
        return video
    except NoResultFound:
        raise UnknownVideo()


def get_video_for_app(video_id: int) -> Tuple[dict, Optional[dict], Optional[dict]]:
    """
    Get a Video, with it's prev/next videos.  Mark the Video as viewed.
    """
    with get_db_session(commit=True) as session:
        video = get_video(session, video_id)
        video.set_viewed()
        previous_video, next_video = video.get_surrounding_videos()

        caption = video.video_file.d_text
        video = video.video_file.__json__()
        video['video']['caption'] = caption
        previous_video = previous_video.video_file.__json__() if previous_video and previous_video.video_file else None
        next_video = next_video.video_file.__json__() if next_video and next_video.video_file else None

    return video, previous_video, next_video


VIDEO_ORDERS = {
    'upload_date': 'v.upload_date ASC, LOWER(v.video_path) ASC',
    '-upload_date': 'v.upload_date DESC NULLS LAST, LOWER(v.video_path) DESC',
    'rank': '2 DESC, LOWER(v.video_path) DESC',
    '-rank': '2 ASC, LOWER(v.video_path) ASC',
    'id': 'v.id ASC',
    '-id': 'v.id DESC',
    'size': 'f.size ASC, LOWER(v.video_path) ASC',
    '-size': 'f.size DESC, LOWER(v.video_path) DESC',
    'duration': 'duration ASC, LOWER(v.video_path) ASC',
    '-duration': 'duration DESC, LOWER(v.video_path) DESC',
    'favorite': 'favorite ASC, LOWER(v.video_path) ASC',
    '-favorite': 'favorite DESC, LOWER(v.video_path) DESC',
    'viewed': 'v.viewed ASC',
    '-viewed': 'v.viewed DESC',
    'view_count': 'v.view_count ASC',
    '-view_count': 'v.view_count DESC',
    'modification_datetime': 'f.modification_datetime ASC',
    '-modification_datetime': 'f.modification_datetime DESC',
}
NO_NULL_ORDERS = {
    'viewed': 'v.viewed IS NOT NULL',
    '-viewed': 'v.viewed IS NOT NULL',
    'duration': 'v.duration IS NOT NULL',
    '-duration': 'v.duration IS NOT NULL',
    'size': 'f.size IS NOT NULL',
    '-size': 'f.size IS NOT NULL',
    'view_count': 'v.view_count IS NOT NULL',
    '-view_count': 'v.view_count IS NOT NULL',
    'modification_datetime': 'f.modification_datetime IS NOT NULL',
    '-modification_datetime': 'f.modification_datetime IS NOT NULL',
}
DEFAULT_VIDEO_ORDER = 'rank'
VIDEO_QUERY_LIMIT = 24


def search_videos(
        search_str: str = None,
        offset: int = None,
        limit: int = VIDEO_QUERY_LIMIT,
        channel_id: int = None,
        order_by: str = None,
        filters: List[str] = None,
) -> Tuple[List[dict], int]:
    filters = filters or []
    wheres = ['v.video_path IS NOT NULL']

    params = dict(search_str=search_str, offset=offset)
    if channel_id:
        wheres.append('v.channel_id = %(channel_id)s')
        params['channel_id'] = channel_id

    # Apply filters.
    if 'favorite' in filters:
        wheres.append('v.favorite IS NOT NULL')
    if 'censored' in filters:
        wheres.append('v.censored = true')

    if search_str:
        # A search_str was provided by the user, modify the query to filter by it.
        select_columns = 'f.path, ts_rank(f.textsearch, websearch_to_tsquery(%(search_str)s)), ' \
                         'COUNT(*) OVER() AS total'
        wheres.append('f.textsearch @@ websearch_to_tsquery(%(search_str)s)')
        params['search_str'] = search_str
        join = 'LEFT JOIN file f on f.path = v.video_path'
    else:
        # No search_str provided.  Get path and total only.
        select_columns = 'v.video_path AS path, COUNT(*) OVER() AS total'
        join = ''

    if order_by in {'size', '-size', 'modification_datetime', '-modification_datetime'}:
        # Size and modification_datetime are from the video file.
        join = 'LEFT JOIN file f on f.path = v.video_path'

    # Convert the user-friendly order by into a real order by, restrict what can be interpolated by using the
    # whitelist.
    order = VIDEO_ORDERS[DEFAULT_VIDEO_ORDER]
    if order_by:
        try:
            order = VIDEO_ORDERS[order_by]
        except KeyError:
            raise
        if order_by in NO_NULL_ORDERS:
            wheres.append(NO_NULL_ORDERS[order_by])

    wheres = '\n AND '.join(wheres)
    where = f'WHERE\n{wheres}' if wheres else ''
    stmt = f'''
        SELECT
            {select_columns}
        FROM video v
        {join}
        {where}
        ORDER BY {order}
        OFFSET %(offset)s LIMIT {int(limit)}
    '''.strip()
    logger.debug(stmt, params)

    results, total = handle_search_results(stmt, params)
    return results, total


@run_after(save_channels_config)
def set_video_favorite(video_id: int, favorite: bool) -> Optional[datetime]:
    """
    Set the Video.favorite to the current datetime if `favorite` is True, otherwise None.
    """
    with get_db_session(commit=True) as session:
        video = session.query(Video).filter_by(id=video_id).one()
        favorite = video.set_favorite(favorite)

    return favorite


@optional_session
def delete_videos(*video_ids: int, session: Session = None):
    videos = list(session.query(Video).filter(Video.id.in_(video_ids)))
    if not videos:
        raise UnknownVideo('Could not find videos to delete')

    logger.warning(f'Deleting {len(videos)} videos')
    for video in videos:
        video.delete()
    session.commit()
