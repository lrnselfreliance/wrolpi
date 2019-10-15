#! /usr/bin/env python3
from typing import Generator

import webvtt
from dictorm import DictDB, Dict


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
    caption_path = video['caption_path']
    if not caption_path:
        raise UnknownCaptionFile(f'No caption file specified for video record {video["id"]}')

    lines = get_unique_caption_lines(caption_path)
    block = '\n'.join(lines)
    curs = video.table.db.get_cursor()
    curs.execute('UPDATE video SET caption = %s WHERE id=%s', (block, video['id']))
