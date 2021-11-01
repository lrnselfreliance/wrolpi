#! /usr/bin/env python3
from pathlib import Path
from typing import Generator, List, Union

import srt
import webvtt

from wrolpi.common import logger, chunks
from wrolpi.db import get_db_session
from wrolpi.errors import UnknownCaptionFile
from .common import get_absolute_video_caption
from .models import Video


def get_caption_text(caption_path: Union[str, Path]) -> Generator:
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


def get_unique_caption_lines(caption_path: Union[str, Path]) -> Generator:
    """
    Return all unique lines from each caption of a caption file.
    """
    last_line = None
    for text in get_caption_text(caption_path):
        for line in text.split('\n'):
            if line and line != last_line:
                last_line = line
                yield line


def process_captions(video: Video):
    """
    Parse and insert captions for a video record.
    """
    caption_path = get_absolute_video_caption(video)
    if not caption_path.exists():
        raise UnknownCaptionFile()
    try:
        lines = get_unique_caption_lines(str(caption_path))
        block = '\n'.join(lines)
        video.caption = block
        return
    except UnicodeDecodeError:
        # Failed to decode the caption file
        # TODO handle this error
        pass
    except webvtt.errors.MalformedFileError:
        # File format is broken
        pass
    except webvtt.errors.MalformedCaptionError:
        # Captions form is broken somehow
        pass

    logger.debug(f'Failed to parse caption file {caption_path}')


async def insert_bulk_captions(video_ids: List[int]):
    for video_ids in chunks(video_ids, 10):
        with get_db_session(commit=True) as session:
            for idx, video_id in enumerate(video_ids):
                video = session.query(Video).filter_by(id=video_id).one()
                process_captions(video)
    logger.debug(f'Inserted {len(video_ids)} captions')
