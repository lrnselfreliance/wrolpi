from datetime import datetime
from typing import Tuple, Optional, List, Set

import cachetools
import psycopg2
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import NoResultFound

from wrolpi.common import run_after, logger
from wrolpi.db import get_db_session, get_db_curs
from wrolpi.errors import UnknownVideo, UnknownChannel
from wrolpi.vars import PYTEST
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
            if PYTEST:
                # Bypass cache for testing only.
                params['censored_source_ids'] = list(_censored_source_ids(channel_link))
            else:
                params['censored_source_ids'] = list(censored_source_ids(channel_link))
            censored_where = 'AND source_id = ANY(%(censored_source_ids)s)'

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

    with get_db_session() as session:
        results = []
        if ranked_ids:
            results = session.query(Video).filter(Video.id.in_(ranked_ids)).all()
            results = sorted(results, key=lambda r: ranked_ids.index(r.id))

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


def _censored_source_ids(link: str = None) -> Set[str]:
    with get_db_curs() as curs:
        if link:
            curs.execute('SELECT id FROM channel WHERE link=%s', (link,))
            try:
                id_ = curs.fetchone()[0]
            except TypeError:
                raise UnknownChannel(f'No channel {link}')

            curs.execute("SELECT info_json->'entries' FROM channel WHERE info_json IS NOT NULL AND link=%s", (link,))
            try:
                entries = curs.fetchone()[0]
            except TypeError:
                # Channel has no info_json entries, so we can't find censored.
                return set()

            source_ids = {i['id'] for i in entries if i}
            curs.execute('SELECT source_id FROM video WHERE channel_id =%s', (id_,))
            our_source_ids = {i[0] for i in curs.fetchall()}
        else:
            curs.execute("SELECT info_json->'entries' FROM channel WHERE info_json IS NOT NULL")
            source_ids = {j['id'] for i in curs.fetchall() if i and i[0] for j in i[0]}
            stmt = '''
                SELECT v.source_id
                FROM video v
                WHERE v.channel_id IN (select id from channel c where info_json is not null)
            '''
            curs.execute(stmt)
            result = curs.fetchall()
            our_source_ids = {i[0] for i in result}

        censored_ids = our_source_ids - source_ids
        return censored_ids


@cachetools.cached(cachetools.TTLCache(maxsize=100, ttl=600))
def censored_source_ids(link: str = None) -> Set[str]:
    """
    Get all Videos that are downloaded, but are not in its Channel's catalog.  Videos without a channel will not be
    returned.
    """
    return _censored_source_ids(link)
