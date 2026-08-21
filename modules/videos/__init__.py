import asyncio
import json
import pathlib
from typing import Callable, List, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session

from modules.videos.common import get_or_create_ffprobe_json
from modules.videos.models import Video, AUDIO_PLAYLIST_MIMETYPES
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
    # Ids that failed to model this run.  A failure leaves no Video row, so the `Video.id IS
    # NULL` gate below would re-select it forever; failures are retried on the next refresh.
    failed_ids: set = set()
    while True:
        # Read the batch; nothing is claimed yet, so the write lock stays free while ffprobe runs.
        with get_db_session() as session:
            query = session.query(FileGroup.id, FileGroup.primary_path) \
                .outerjoin(Video, Video.file_group_id == FileGroup.id) \
                .filter(
                or_(FileGroup.mimetype.like('video/%'), FileGroup.mimetype.like('audio/%')),
                FileGroup.mimetype.notin_(AUDIO_PLAYLIST_MIMETYPES),
                # Model anything without a Video row, even if something else (an upload, an
                # indexer) already set `indexed=True` -- gating solely on `indexed == False`
                # left such files permanently invisible in their Channels.
                or_(Video.id.is_(None), FileGroup.indexed != True),
            )
            if failed_ids:
                query = query.filter(FileGroup.id.notin_(failed_ids))
            batch: List[Tuple[int, pathlib.Path]] = list(query.limit(VIDEO_PROCESSING_LIMIT).all())

        if not batch:
            break

        # ffprobe each file with no transaction open.  This is a subprocess per video and can run
        # for seconds; inside the write transaction below it would hold the write lock for the whole
        # batch, and every other writer on the box would wait out `busy_timeout` (30s).
        probed = dict()
        for file_group_id, primary_path in batch:
            try:
                probed[file_group_id] = await get_or_create_ffprobe_json(pathlib.Path(str(primary_path)))
            except Exception as e:
                if PYTEST:
                    raise
                logger.error(f'Unable to ffprobe Video: {primary_path}', exc_info=e)
            # Sleep to catch cancel.
            await asyncio.sleep(0)

        with get_db_session(commit=True) as session:
            file_groups: List[Tuple[FileGroup, Video]] = list(
                session.query(FileGroup, Video)
                .filter(FileGroup.id.in_([i for i, _ in batch]))
                .outerjoin(Video, Video.file_group_id == FileGroup.id))

            for file_group, video in file_groups:
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
                    # Store the ffprobe data gathered above.
                    if (result := probed.get(file_group.id)) is not None:
                        video.ffprobe_json, ffprobe_file = result
                        if ffprobe_file:
                            # Track the .ffprobe.json cache file that was just written.
                            file_group.append_files(ffprobe_file)
                    video.flush(session)
                    # Validate and index subtitles.  (Poster generation happens here when a Channel
                    # asks for it; it is the remaining slow work inside this transaction.)
                    video.validate(session)
                except Exception as e:
                    if PYTEST:
                        raise
                    failed_ids.add(file_group.id)
                    i = video.file_group.primary_path if video.file_group else video_id
                    logger.error(f'Unable to model Video: {str(i)}', exc_info=e)

                file_group.indexed = True

        # Report batch progress
        total_processed += len(batch)
        if progress_callback:
            progress_callback(total_processed)

        logger.debug(f'Modeled {len(batch)} videos')

        if len(batch) < VIDEO_PROCESSING_LIMIT:
            # Did not reach limit, do not query again.
            break

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
                                 INNER JOIN collection col
                                            ON (fg.directory = col.directory
                                                OR fg.directory LIKE col.directory || '/%')
                                 INNER JOIN channel c ON c.collection_id = col.id
                        WHERE v.channel_id IS NULL
                        '''


@register_refresh_cleanup
@limit_concurrent(1)
def video_cleanup():
    logger.info('Claiming Videos for their Channels')
    # Read the FileGroups that are no longer video/audio (audio playlists never were),
    # then unmodel them in short transactions.
    with get_db_curs() as curs:
        playlists = ', '.join(f"'{mt}'" for mt in AUDIO_PLAYLIST_MIMETYPES)
        curs.execute(f'''
                     SELECT id
                     FROM file_group
                     WHERE model = 'video'
                       AND ((mimetype NOT LIKE 'video/%' AND mimetype NOT LIKE 'audio/%')
                         OR mimetype IN ({playlists}))
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
