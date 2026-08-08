import asyncio
import json
from typing import Callable, List, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session

from modules.videos.models import Video
from wrolpi.common import logger, limit_concurrent, register_modeler, register_refresh_cleanup
from wrolpi.db import get_db_curs, get_db_session
from wrolpi.files.models import FileGroup
from wrolpi.vars import PYTEST
from .downloader import video_downloader  # Import downloaders so they are registered.

logger = logger.getChild(__name__)

__all__ = ['video_modeler']

VIDEO_PROCESSING_LIMIT = 20


@register_modeler
async def video_modeler(progress_callback: Callable[[int], None] = None):
    total_processed = 0
    while True:
        with get_db_session(commit=True) as session:
            file_groups = session.query(FileGroup, Video).filter(
                FileGroup.indexed != True,
                or_(FileGroup.mimetype.like('video/%'), FileGroup.mimetype.like('audio/%')),
            ).outerjoin(Video, Video.file_group_id == FileGroup.id) \
                .limit(VIDEO_PROCESSING_LIMIT)
            file_groups: List[Tuple[FileGroup, Video]] = list(file_groups)

            processed = 0
            for file_group, video in file_groups:
                processed += 1

                video_id = None
                try:
                    if not video:
                        video = Video(file_group=file_group, file_group_id=file_group.id)
                        session.add(video)
                        session.flush([video])
                    video_id = video.id
                    if not Session.object_session(video):
                        session.add(video)
                        video.flush()
                    # Extract ffprobe data.
                    await video.get_ffprobe_json()
                    video.flush(session)
                    # Validate and index subtitles.
                    video.validate(session)
                    processed += 1
                except Exception as e:
                    if PYTEST:
                        raise
                    i = video.file_group.primary_path if video.file_group else video_id
                    logger.error(f'Unable to model Video: {str(i)}', exc_info=e)

                file_group.indexed = True

            session.commit()

            # Report batch progress
            total_processed += len(file_groups)
            if progress_callback and len(file_groups) > 0:
                progress_callback(total_processed)

            if processed < VIDEO_PROCESSING_LIMIT:
                # Did not reach limit, do not query again.
                break

            logger.debug(f'Modeled {processed} videos')

        # Sleep to catch cancel.
        await asyncio.sleep(0)


# Rows written per transaction when claiming Videos for their Channels.  Small enough that the
# write lock is held for milliseconds at a time; large enough that a big library does not pay a
# transaction per row.
CLAIM_CHUNK_SIZE = 500


def _chunks(items: list, size: int = CLAIM_CHUNK_SIZE):
    for start in range(0, len(items), size):
        yield items[start:start + size]


def _first_claim_per_video(rows) -> List[Tuple[int, int]]:
    """One `(video_id, channel_id)` per Video.

    A Video nested under two Channel directories matches both; the single `UPDATE ... FROM` this
    replaced also picked one arbitrarily, so keep the first row and drop the rest rather than
    writing the same Video twice."""
    claims = dict()
    for video_id, channel_id in rows:
        claims.setdefault(video_id, channel_id)
    return list(claims.items())


def _claim_videos(claims: List[Tuple[int, int]]):
    """Assign `(video_id, channel_id)` pairs, a chunk per write transaction.

    The pairs are computed by a *read* — WAL readers never block writers — and only these short
    UPDATEs take the write lock.  Doing the whole thing as one `UPDATE ... FROM channel` held the
    lock for the entire join: 110-130 seconds per refresh on a library with ~1500 channels, which
    is well past the 30s `busy_timeout`, so every other writer on the box failed with "database is
    locked" for two solid minutes.

    `channel_id IS NULL` is re-checked in the UPDATE because the read ran in an earlier
    transaction: a download may have claimed the Video since, and it should win.
    """
    if not claims:
        return
    claimed = 0
    for chunk in _chunks(claims):
        with get_db_curs(commit=True) as curs:
            curs.executemany('UPDATE video SET channel_id = ? WHERE id = ? AND channel_id IS NULL',
                             [(channel_id, video_id) for video_id, channel_id in chunk])
        claimed += len(chunk)
    logger.debug(f'Claimed {claimed} Videos for their Channels')


# Videos in a Channel's directory (or below it) that no Channel has claimed yet.
_UNCLAIMED_VIDEOS_SQL = '''
                        SELECT v.id, c.id
                        FROM video v
                                 INNER JOIN file_group fg ON fg.id = v.file_group_id
                                 INNER JOIN collection col ON fg.directory = col.directory
                            OR fg.directory LIKE col.directory || '/%'
                                 INNER JOIN channel c ON c.collection_id = col.id
                        WHERE v.channel_id IS NULL
                        '''


@register_refresh_cleanup
@limit_concurrent(1)
def video_cleanup():
    logger.info('Claiming Videos for their Channels')
    # Read the FileGroups that are no longer video/audio, then unmodel them in short transactions.
    with get_db_curs() as curs:
        curs.execute('''
                     SELECT id
                     FROM file_group
                     WHERE model = 'video'
                       AND mimetype NOT LIKE 'video/%'
                       AND mimetype NOT LIKE 'audio/%'
                     ''')
        stale_ids = [i['id'] for i in curs.fetchall()]
    for chunk in _chunks(stale_ids):
        ids = json.dumps(chunk)
        with get_db_curs(commit=True) as curs:
            curs.execute('''
                         UPDATE file_group
                         SET model = NULL
                         WHERE id IN (SELECT value FROM json_each(:ids))
                         ''', dict(ids=ids))
            curs.execute('''
                         DELETE
                         FROM video
                         WHERE file_group_id IN (SELECT value FROM json_each(:ids))
                         ''', dict(ids=ids))

    # Claim all Videos in a Channel's directory for that Channel.  But, only if they have not yet
    # been claimed.  The join is the slow part, so it runs as a read; only the writes take the lock.
    with get_db_curs() as curs:
        curs.execute(_UNCLAIMED_VIDEOS_SQL)
        claims = _first_claim_per_video(curs.fetchall())
    _claim_videos(claims)



def claim_videos_for_channels(channel_ids: List[int]):
    """
    Assign Videos to specific Channels based on directory paths.

    This is a targeted version of video_cleanup() that only processes specific channel IDs.
    More efficient than video_cleanup() for channel import because it limits the scope
    of the SQL update to only the channels that were just imported/updated.

    Args:
        channel_ids: List of channel IDs to process
    """
    if not channel_ids:
        return

    logger.info(f'Claiming Videos for {len(channel_ids)} channel(s)')
    # Read the claims, then write them in chunks -- the join must not hold the write lock (see
    # `_claim_videos`).  Channel import calls this with every channel in channels.yaml, so it is
    # just as slow as the full `video_cleanup` sweep.
    with get_db_curs() as curs:
        curs.execute(f'''
                     {_UNCLAIMED_VIDEOS_SQL}
                       AND c.id IN (SELECT value FROM json_each(:channel_ids))
                     ''', dict(channel_ids=json.dumps(list(channel_ids))))
        claims = _first_claim_per_video(curs.fetchall())
    _claim_videos(claims)
