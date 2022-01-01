from datetime import datetime
from typing import Tuple, Optional, List

import psycopg2
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import NoResultFound

from wrolpi.common import run_after, logger
from wrolpi.db import get_db_session, get_db_curs, get_ranked_models
from wrolpi.errors import UnknownVideo
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

        video = video.__json__()
        previous_video = previous_video.__json__() if previous_video else None
        next_video = next_video.__json__() if next_video else None

    return video, previous_video, next_video


VIDEO_ORDERS = {
    'upload_date': 'upload_date ASC, LOWER(video_path) ASC',
    '-upload_date': 'upload_date DESC NULLS LAST, LOWER(video_path) DESC',
    'rank': '2 DESC, LOWER(video_path) DESC',
    '-rank': '2 ASC, LOWER(video_path) ASC',
    'id': 'id ASC',
    '-id': 'id DESC',
    'size': 'size ASC, LOWER(video_path) ASC',
    '-size': 'size DESC, LOWER(video_path) DESC',
    'duration': 'duration ASC, LOWER(video_path) ASC',
    '-duration': 'duration DESC, LOWER(video_path) DESC',
    'favorite': 'favorite ASC, LOWER(video_path) ASC',
    '-favorite': 'favorite DESC, LOWER(video_path) DESC',
    'viewed': 'viewed ASC',
    '-viewed': 'viewed DESC',
    'view_count': 'view_count ASC',
    '-view_count': 'view_count DESC',
}
NO_NULL_ORDERS = {
    'viewed': '\nAND viewed IS NOT NULL',
    '-viewed': '\nAND viewed IS NOT NULL',
    'duration': '\nAND duration IS NOT NULL',
    '-duration': '\nAND duration IS NOT NULL',
    'size': '\nAND size IS NOT NULL',
    '-size': '\nAND size IS NOT NULL',
    'view_count': '\nAND view_count IS NOT NULL',
    '-view_count': '\nAND view_count IS NOT NULL',
}
DEFAULT_VIDEO_ORDER = 'rank'
VIDEO_QUERY_LIMIT = 20


def video_search(
        search_str: str = None,
        offset: int = None,
        limit: int = VIDEO_QUERY_LIMIT,
        channel_link: str = None,
        order_by: str = None,
        filters: List[str] = None,
) -> Tuple[List[dict], int]:
    with get_db_curs() as curs:
        params = dict(search_str=search_str, offset=offset)
        channel_where = ''
        if channel_link:
            channel_where = 'AND channel_id = (select id from channel where link=%(channel_link)s)'
            params['channel_link'] = channel_link

        # Filter for/against favorites, if it was provided
        favorites_where = ''
        if isinstance(filters, list) and 'favorite' in filters:
            favorites_where = 'AND favorite IS NOT NULL'

        censored_where = ''
        if isinstance(filters, list) and 'censored' in filters:
            censored_where = 'AND censored = true'

        where = ''
        if search_str:
            # A search_str was provided by the user, modify the query to filter by it.
            columns = 'id, ts_rank_cd(textsearch, websearch_to_tsquery(%(search_str)s)), COUNT(*) OVER() AS total'
            where = 'AND textsearch @@ websearch_to_tsquery(%(search_str)s)'
            params['search_str'] = search_str
        else:
            # No search_str provided.  Get id and total only.
            columns = 'id, COUNT(*) OVER() AS total'

        # Convert the user-friendly order by into a real order by, restrict what can be interpolated by using the
        # whitelist.
        order = VIDEO_ORDERS[DEFAULT_VIDEO_ORDER]
        if order_by:
            try:
                order = VIDEO_ORDERS[order_by]
            except KeyError:
                raise
            if order_by in NO_NULL_ORDERS:
                where += NO_NULL_ORDERS[order_by]

        query = f'''
            SELECT
                {columns}
            FROM video
            WHERE
                video_path IS NOT NULL
                {where}
                {channel_where}
                {favorites_where}
                {censored_where}
            ORDER BY {order}
            OFFSET %(offset)s LIMIT {int(limit)}
        '''.strip()
        logger.debug(query)

        curs.execute(query, params)
        try:
            results = [dict(i) for i in curs.fetchall()]
        except psycopg2.ProgrammingError:
            # No videos
            return [], 0
        total = results[0]['total'] if results else 0
        ranked_ids = [i['id'] for i in results]

    results = get_ranked_models(ranked_ids, Video)
    results = [i.__json__() for i in results]

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
