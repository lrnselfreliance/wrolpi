from datetime import datetime
from typing import Tuple, Optional, List

from dictorm import Dict, DictDB

from api.db import get_db_context
from api.errors import UnknownVideo, UnknownFile
from api.videos.common import get_absolute_video_files, add_video_to_skip_list
from api.videos.video.api import logger


def get_video(db, video_id: int) -> Dict:
    Video = db['video']
    video = Video.get_one(id=video_id)
    if not video:
        raise UnknownVideo()
    _ = video['channel']
    return video


def get_surrounding_videos(db: DictDB, video_id: int, channel_id: int) -> Tuple[Optional[Dict], Optional[Dict]]:
    """
    Get the previous and next videos around the provided video.  The videos must be in the same channel.

    Example:
        vid1 = Video(id=1, upload_date=10)
        vid2 = Video(id=2, upload_date=20)
        vid3 = Video(id=3, upload_date=30)
        vid4 = Video(id=4)

        >>> get_surrounding_videos(video_id=1, ...)
        (None, vid2)
        >>> get_surrounding_videos(video_id=2, ...)
        (vid1, vid3)
        >>> get_surrounding_videos(video_id=3, ...)
        (vid2, None)
        Video 4 has no upload date, so we can't place it in order.
        >>> get_surrounding_videos(video_id=4, ...)
        (None, None)
    """
    video_id, channel_id = int(video_id), int(channel_id)

    curs = db.get_cursor()

    query = '''
            WITH numbered_videos AS (
                SELECT id,
                    ROW_NUMBER() OVER (ORDER BY upload_date ASC) AS row_number
                FROM video
                WHERE
                    channel_id = %(channel_id)s
                    AND upload_date IS NOT NULL
            )

            SELECT id
            FROM numbered_videos
            WHERE row_number IN (
                SELECT row_number+i
                FROM numbered_videos
                CROSS JOIN (SELECT -1 AS i UNION ALL SELECT 0 UNION ALL SELECT 1) n
                WHERE
                id = %(video_id)s
            )
    '''
    curs.execute(query, dict(channel_id=channel_id, video_id=video_id))
    results = [i[0] for i in curs.fetchall()]

    # Assign the returned ID's to their respective positions relative to the ID that matches the video_id.
    previous_id = next_id = None
    for idx, id_ in enumerate(results):
        if id_ == video_id:
            if idx > 0:
                previous_id = results[idx - 1]
            if idx + 1 < len(results):
                next_id = results[idx + 1]
            break

    # Fetch the videos by id, if they exist.
    Video = db['video']
    previous_video = Video.get_one(id=previous_id) if previous_id else None
    next_video = Video.get_one(id=next_id) if next_id else None

    return previous_video, next_video


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
        db: DictDB,
        search_str: str = None,
        offset: int = None,
        limit: int = VIDEO_QUERY_LIMIT,
        channel_link: str = None,
        order_by: str = None,
        favorites: bool = None,
) -> Tuple[List[Dict], int]:
    curs = db.get_cursor()

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
    '''
    logger.debug(query)

    curs.execute(query, args)
    results = [dict(i) for i in curs.fetchall()]
    total = results[0]['total'] if results else 0
    ranked_ids = [i['id'] for i in results]

    results = []
    if ranked_ids:
        Video = db['video']
        results = Video.get_where(Video['id'].In(ranked_ids))
        results = sorted(results, key=lambda r: ranked_ids.index(r['id']))
    return results, total


def set_video_favorite(video_id: int, favorite: bool) -> Optional[datetime]:
    """
    Toggle the timestamp on Video.favorite on a video.
    """
    with get_db_context(commit=True) as (db_conn, db):
        Video = db['video']
        video = Video.get_one(id=video_id)
        _favorite = video['favorite'] = datetime.now() if favorite else None
        video.flush()

    return _favorite


def delete_video(video: Dict):
    """
    Delete any and all video files for a particular video.  If deletion succeeds, mark it as "do-not-download".
    """
    video_files = get_absolute_video_files(video)
    for path in video_files:
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    if not video_files:
        raise UnknownFile('No video files were deleted')

    with get_db_context(commit=True) as (db_conn, db):
        Video = db['video']
        video = Video.get_one(id=video['id'])

        video['video_path'] = None
        video['poster_path'] = None
        video['caption_path'] = None
        video['description_path'] = None
        video['info_json_path'] = None
        video.flush()

        channel = video['channel']
        add_video_to_skip_list(channel, video)
