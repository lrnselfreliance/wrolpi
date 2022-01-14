#! /usr/bin/env python3
import pathlib
from pathlib import Path
from typing import Generator, Union

import srt
import webvtt

from wrolpi.common import logger
from wrolpi.media_path import MediaPath
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


def get_video_captions(video: Video):
    """
    Parse video captions from the video's captions file.
    """
    if isinstance(video.caption_path, MediaPath):
        caption_path = video.caption_path.path
    else:
        caption_path = pathlib.Path(video.caption_path)

    try:
        lines = get_unique_caption_lines(str(caption_path))
        block = '\n'.join(lines)
        return block
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
