from datetime import datetime
from typing import Tuple, Optional, List

import psycopg2
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import NoResultFound

from api.db import get_db_context, get_db_curs
from api.errors import UnknownVideo
from api.videos.models import Video
from api.videos.video.api import logger


def get_video(session: Session, video_id: int) -> Video:
    try:
        video = session.query(Video).filter_by(id=video_id).one()
        return video
    except NoResultFound:
        raise UnknownVideo()


def get_video_for_app(video_id: int) -> Tuple[Video, Optional[Video], Optional[Video]]:
    """
    Get a Video, with it's prev/next videos.  Mark the Video as viewed.
    """
    with get_db_context(commit=True) as (engine, session):
        video = get_video(session, video_id)
        video.set_viewed()
        previous_video, next_video = video.get_surrounding_videos()

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
}
NO_NULL_ORDERS = {
    'viewed': '\nAND viewed IS NOT NULL',
    '-viewed': '\nAND viewed IS NOT NULL',
    'duration': '\nAND duration IS NOT NULL',
    '-duration': '\nAND duration IS NOT NULL',
    'size': '\nAND size IS NOT NULL',
    '-size': '\nAND size IS NOT NULL',
}
DEFAULT_VIDEO_ORDER = 'rank'
VIDEO_QUERY_LIMIT = 20


def video_search(
        search_str: str = None,
        offset: int = None,
        limit: int = VIDEO_QUERY_LIMIT,
        channel_link: str = None,
        order_by: str = None,
        favorites: bool = None,
) -> Tuple[List[dict], int]:
    with get_db_curs() as curs:
        args = dict(search_str=search_str, offset=offset)
        channel_where = ''
        if channel_link:
            channel_where = 'AND channel_id = (select id from channel where link=%(channel_link)s)'
            args['channel_link'] = channel_link

        # Filter for/against favorites, if it was provided
        favorites_where = ''
        if favorites is not None:
            favorites_where = f'AND favorite IS {"NOT" if favorites else ""} NULL'

        where = ''
        if search_str:
            # A search_str was provided by the user, modify the query to filter by it.
            columns = 'id, ts_rank_cd(textsearch, websearch_to_tsquery(%(search_str)s)), COUNT(*) OVER() AS total'
            where = 'AND textsearch @@ websearch_to_tsquery(%(search_str)s)'
            args['search_str'] = search_str
        else:
            # No search_str provided.  Get id and total only.
            columns = 'id, COUNT(*) OVER() AS total'

        # Convert the user-friendly order by into a real order by, restrict what can be interpolated by using the whitelist.
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
            ORDER BY {order}
            OFFSET %(offset)s LIMIT {int(limit)}
        '''.strip()
        logger.debug(query)

        curs.execute(query, args)
        try:
            results = [dict(i) for i in curs.fetchall()]
        except psycopg2.ProgrammingError:
            # No videos
            return [], 0
        total = results[0]['total'] if results else 0
        ranked_ids = [i['id'] for i in results]

    with get_db_context() as (engine, session):
        results = []
        if ranked_ids:
            results = session.query(Video).filter(Video.id.in_(ranked_ids)).all()
            results = sorted(results, key=lambda r: ranked_ids.index(r.id))

        results = [i.get_minimize() for i in results]

    return results, total


def set_video_favorite(video_id: int, favorite: bool) -> Optional[datetime]:
    """
    Toggle the timestamp on Video.favorite on a video.
    """
    with get_db_context(commit=True) as (engine, session):
        video = session.query(Video).filter_by(id=video_id).one()
        return video.set_favorite(favorite)
