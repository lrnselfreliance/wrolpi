import asyncio
from typing import List, Tuple

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
async def video_modeler():
    while True:
        with get_db_session(commit=True) as session:
            file_groups = session.query(FileGroup, Video).filter(
                FileGroup.indexed != True,
                FileGroup.mimetype.like('video/%'),
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

            if processed < VIDEO_PROCESSING_LIMIT:
                # Did not reach limit, do not query again.
                break

            logger.debug(f'Modeled {processed} videos')

        # Sleep to catch cancel.
        await asyncio.sleep(0)


@register_refresh_cleanup
@limit_concurrent(1)
def video_cleanup():
    logger.info('Claiming Videos for their Channels')
    with get_db_curs(commit=True) as curs:
        # Delete all Videos if the FileModel no longer contains a video.
        curs.execute('''
            WITH deleted AS
             (UPDATE file_group SET model=null WHERE model='video' AND mimetype NOT LIKE 'video/%' RETURNING id)
             DELETE FROM video WHERE file_group_id = ANY(select id from deleted)
        ''')
        # Claim all Videos in a Channel's directory for that Channel.  But, only if they have not yet been claimed.
        curs.execute('''
            UPDATE video v
            SET
                channel_id = c.id
            FROM channel c
                LEFT JOIN file_group fg ON fg.primary_path LIKE c.directory || '/%'::VARCHAR
            WHERE
             v.channel_id IS NULL
             AND fg.id = v.file_group_id
        ''')
