#! /usr/bin/env python3
from typing import Generator, List

import srt
import webvtt
from dictorm import Dict

from api.common import logger
from api.errors import UnknownCaptionFile
from .common import get_absolute_video_caption
from ..db import get_db_context


def get_caption_text(caption_path: str) -> Generator:
    """
    Return all text from each caption of a caption file.
    """
    if str(caption_path).endswith('vtt'):
        for caption in webvtt.read(caption_path):
            text = str(caption.text).strip()
            yield text
    else:
        with open(caption_path, 'rt') as fh:
            contents = fh.read()
            for subtitle in srt.parse(contents):
                yield subtitle.content


def get_unique_caption_lines(caption_path: str) -> Generator:
    """
    Return all unique lines from each caption of a caption file.
    """
    last_line = None
    for text in get_caption_text(caption_path):
        for line in text.split('\n'):
            if line and line != last_line:
                last_line = line
                yield line


def process_captions(video: Dict):
    """
    Parse and insert captions for a video record.
    """
    caption_path = get_absolute_video_caption(video)
    if not caption_path.exists():
        raise UnknownCaptionFile()
    try:
        lines = get_unique_caption_lines(str(caption_path))
        block = '\n'.join(lines)
        video['caption'] = block
        video.flush()
    except UnicodeDecodeError:
        # Failed to decode the caption file
        # TODO handle this error
        logger.debug(f'Failed to decode caption file {caption_path}')
    except webvtt.errors.MalformedFileError:
        # File format is broken
        logger.debug(f'Failed to parse caption file {caption_path}')


async def insert_bulk_captions(video_ids: List[int]):
    with get_db_context(commit=True) as (db_conn, db):
        Video = db['video']
        for idx, video_id in enumerate(video_ids):
            video = Video.get_one(id=video_id)
            process_captions(video)
    logger.debug(f'Inserted {len(video_ids)} captions')
