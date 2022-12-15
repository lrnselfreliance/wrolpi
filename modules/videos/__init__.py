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
from wrolpi.files.lib import split_path_stem_and_suffix
from wrolpi.files.models import File
from wrolpi.vars import PYTEST
from .downloader import video_downloader  # Import downloaders so they are registered.

logger = logger.getChild(__name__)

__all__ = ['video_modeler', 'VideoIndexer']


def find_video_file_in_group(group: List[File]):
    return next((i for i in group if i.mimetype.startswith('video/') and i.path.suffix != '.part'), None)


@register_modeler
def video_modeler(groups: Dict[str, List[File]], session: Session):
    new_videos = []

    # Search all groups for video files.
    video_files = {stem: video_file for stem, group in groups.items() if
                   (video_file := find_video_file_in_group(group))}
    if not video_files:
        # No videos in these groups.
        return
    # Get all matching Video records (if any) in one query.
    video_paths = [i.path for i in video_files.values()]
    video_records = {i.video_path: i for i in session.query(Video).filter(Video.video_path.in_(video_paths))}

    for stem, video_file in video_files.items():
        group = groups[stem]

        session.flush(group)
        poster_file = info_json_file = caption_file = None
        for file in group:
            if file.mimetype.startswith('image/'):
                poster_file = file
            elif file.path.name.endswith('.info.json'):
                info_json_file = file
            # Prefer WebVTT over SRT.  (SRT cannot be displayed for HTML video).
            elif file.path.name.endswith('.en.vtt'):
                caption_file = file
            elif file.path.name.endswith('.en.srt'):
                caption_file = caption_file or file

        if poster_file:
            poster_file.associated = True
            poster_file.do_stats()
        if caption_file:
            caption_file.associated = True
            caption_file.do_stats()
        if info_json_file:
            info_json_file.associated = True
            info_json_file.do_stats()

        video: Video = video_records.get(video_file.path)
        if not video:
            video = Video(video_file=video_file)
            session.add(video)

        size = video_file.path.stat().st_size

        if poster_file != video.poster_file or \
                caption_file != video.caption_file or \
                info_json_file != video.info_json_file or \
                video.size != size:
            # Files might have been changed.  Re-index.
            video.video_file.indexed = False

        video.poster_file = poster_file
        video.caption_file = caption_file
        video.info_json_file = info_json_file
        video.size = size
        video_file.model = Video.__tablename__

        new_videos.append(video)

    if new_videos:
        session.flush(new_videos)
        for video in new_videos:
            video.video_file.do_index()
            video.validate(session)

            # Remove this group, it will not be processed by other modelers.
            stem, _ = split_path_stem_and_suffix(video.video_path)
            del groups[stem]


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

        # Detect the associated caption files.
        d = None
        if (en_vtt := file.path.with_suffix('.en.vtt')).is_file():
            d = read_captions(en_vtt)
        elif (vtt := file.path.with_suffix('.vtt')).is_file():
            d = read_captions(vtt)
        elif (en_srt := file.path.with_suffix('.en.srt')).is_file():
            d = read_captions(en_srt)
        elif (srt := file.path.with_suffix('.srt')).is_file():
            d = read_captions(srt)
        elif EXTRACT_SUBTITLES:
            d = extract_captions(file.path) or ''

        return a, None, c, d
