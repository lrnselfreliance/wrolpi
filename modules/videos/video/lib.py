from typing import Tuple, Optional, List

from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import NoResultFound

from modules.videos.models import Video
from wrolpi.common import run_after, logger
from wrolpi.db import get_db_session, optional_session
from wrolpi.errors import UnknownVideo
from wrolpi.files.lib import handle_file_group_search_results, tag_names_to_sub_select
from ..lib import save_channels_config

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
        previous_video = previous_video.__json__() if previous_video and previous_video.file_group else None
        next_video = next_video.__json__() if next_video and next_video.file_group else None

    return video, previous_video, next_video


VIDEO_ORDERS = {
    'upload_date': 'v.upload_date ASC, LOWER(fg.primary_path) ASC',
    '-upload_date': 'v.upload_date DESC NULLS LAST, LOWER(fg.primary_path) ASC',
    'rank': '2 DESC, LOWER(fg.primary_path) DESC',
    '-rank': '2 ASC, LOWER(fg.primary_path) ASC',
    'size': 'fg.size ASC, LOWER(fg.primary_path) ASC',
    '-size': 'fg.size DESC, LOWER(fg.primary_path) DESC',
    'duration': 'duration ASC, LOWER(fg.primary_path) ASC',
    '-duration': 'duration DESC, LOWER(fg.primary_path) DESC',
    'viewed': 'v.viewed ASC',
    '-viewed': 'v.viewed DESC',
    'view_count': 'v.view_count ASC',
    '-view_count': 'v.view_count DESC',
    'modification_datetime': 'fg.modification_datetime ASC',
    '-modification_datetime': 'fg.modification_datetime DESC',
}
NO_NULL_ORDERS = {
    'viewed': 'v.viewed IS NOT NULL',
    '-viewed': 'v.viewed IS NOT NULL',
    'duration': 'v.duration IS NOT NULL',
    '-duration': 'v.duration IS NOT NULL',
    'size': 'fg.size IS NOT NULL',
    '-size': 'fg.size IS NOT NULL',
    'view_count': 'v.view_count IS NOT NULL',
    '-view_count': 'v.view_count IS NOT NULL',
    'modification_datetime': 'fg.modification_datetime IS NOT NULL',
    '-modification_datetime': 'fg.modification_datetime IS NOT NULL',
}
JOIN_ORDERS = ('upload_date', '-upload_date', 'viewed', '-viewed', 'view_count', '-view_count', 'duration', '-duration')
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

    if tag_names:
        # Filter all FileGroups by those that have been tagged with the provided tag names.
        tags_stmt, params_ = tag_names_to_sub_select(tag_names)
        params.update(params_)
        wheres.append(f'fg.id = ANY({tags_stmt})')

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
def tag_video(video_id: int, tag_name: str):
    """Tag a video"""
    with get_db_session(commit=True):
        video = Video.find_by_id(video_id)
        video.add_tag(tag_name)


@optional_session
def delete_videos(*video_ids: int, session: Session = None):
    videos = list(session.query(Video).filter(Video.id.in_(video_ids)))
    if not videos:
        raise UnknownVideo('Could not find videos to delete')

    logger.warning(f'Deleting {len(videos)} videos')
    for video in videos:
        video.delete()
    session.commit()
