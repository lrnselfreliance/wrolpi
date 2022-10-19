import json
import pathlib
from abc import ABC
from typing import List, Dict

from sqlalchemy.orm import Session

from modules.videos.models import Video, Channel
from wrolpi.captions import read_captions, extract_captions
from wrolpi.common import logger, register_modeler, register_after_refresh, limit_concurrent
from wrolpi.db import get_db_curs
from wrolpi.files.indexers import Indexer, register_indexer
from wrolpi.files.models import File
from wrolpi.vars import PYTEST
from .downloader import video_downloader  # Import downloaders so they are registered.

logger = logger.getChild(__name__)

__all__ = ['video_modeler', 'VideoIndexer']


@register_modeler
def video_modeler(groups: Dict[str, List[File]], session: Session):
    local_groups = groups.copy()
    videos = []
    for stem, group in local_groups.items():
        video_file = next((i for i in group if i.mimetype.startswith('video/') and i.path.suffix != '.part'), None)
        if not video_file:
            # Not a video group.
            continue

        session.flush(group)
        poster_file = next((i for i in group if i.mimetype.split('/')[0] == 'image'), None)
        caption_file = next((i for i in group if i.path.name.endswith('.en.vtt') or i.path.name.endswith('.en.srt')),
                            None)
        info_json_file = next((i for i in group if i.path.name.endswith('.info.json')), None)

        if poster_file:
            poster_file.associated = True
            poster_file.do_stats()
        if caption_file:
            caption_file.associated = True
            caption_file.do_stats()
        if info_json_file:
            info_json_file.associated = True
            info_json_file.do_stats()

        video = session.query(Video).filter_by(video_file=video_file).one_or_none()
        if not video:
            video = Video(video_file=video_file)
            session.add(video)
        video.poster_file = poster_file
        video.caption_file = caption_file
        video.info_json_file = info_json_file
        video.size = video_file.path.stat().st_size
        video_file.model = Video.__tablename__

        videos.append(video)

    if videos:
        session.flush(videos)
        for video in videos:
            video.video_file.do_index()
            video.validate(session)

            # Remove this group, it will not be processed by other modelers.
            del groups[video.video_path.stem]


@register_after_refresh
@limit_concurrent(1)
def video_cleanup():
    # Claim all Videos in a Channel's directory for that Channel.
    logger.info('Claiming Videos for their Channels')
    with get_db_curs(commit=True) as curs:
        curs.execute('''
            UPDATE video v
            SET channel_id = c.id
            FROM channel c
            WHERE
             v.video_path LIKE c.directory || '/%'::VARCHAR
             AND v.channel_id IS NULL
        ''')


EXTRACT_SUBTITLES = False


@register_indexer('video')
class VideoIndexer(Indexer, ABC):
    """Handles video files like mp4/ogg."""

    @staticmethod
    def get_description(file):
        video_path: pathlib.Path = file.path.path if hasattr(file.path, 'path') else file.path
        info_json_path = video_path.with_suffix('.info.json')
        if info_json_path.is_file():
            with info_json_path.open('rt') as fh:
                try:
                    return json.load(fh)['description']
                except Exception:
                    if not PYTEST:
                        logger.warning(f'Video info json file exists, but cannot get description. {file}')
                    return None

    @classmethod
    def create_index(cls, file):
        """
        Index the video file and it's associated files.

        a = title.
        b = <empty>
        c = description from info json.
        d = captions from info json, or extracted from video file.
        """
        a = cls.get_title(file)
        c = cls.get_description(file)

        # Detect the associated caption file.
        caption_path = file.path.with_suffix('.en.vtt')
        d = None
        if caption_path.is_file():
            d = read_captions(caption_path)
        elif EXTRACT_SUBTITLES:
            d = extract_captions(file.path) or ''

        return a, None, c, d
