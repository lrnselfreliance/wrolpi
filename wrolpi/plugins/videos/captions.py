#! /usr/bin/env python3
from typing import Generator

import webvtt
from dictorm import Dict

from wrolpi.plugins.videos.common import get_absolute_video_caption


def get_caption_text(vtt_path: str) -> Generator:
    """
    Return all text from each caption of a vtt file.
    """
    for caption in webvtt.read(vtt_path):
        text = str(caption.text).strip()
        yield text


def get_unique_caption_lines(vtt_path: str) -> Generator:
    """
    Return all unique lines from each caption of a vtt file.
    """
    last_line = None
    for text in get_caption_text(vtt_path):
        for line in text.split('\n'):
            if line and line != last_line:
                last_line = line
                yield line


class UnknownCaptionFile(Exception):
    pass


def process_captions(video: Dict):
    """
    Parse and insert captions for a video record.
    """
    caption_path = get_absolute_video_caption(video)
    if not caption_path.exists():
        raise UnknownCaptionFile(f'No caption file for video {video["id"]}')
    try:
        lines = get_unique_caption_lines(str(caption_path))
        block = '\n'.join(lines)
        video['caption'] = block
        video.flush()
    except UnicodeDecodeError:
        # Failed to decode the caption file
        # TODO handle this error
        pass
