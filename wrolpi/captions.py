#! /usr/bin/env python3
import pathlib
import subprocess
import tempfile
from pathlib import Path
from typing import Generator, Union, Optional

import srt
import webvtt

from wrolpi.cmd import FFMPEG_BIN
from wrolpi.common import logger

__all__ = ['read_captions', 'extract_captions']


def get_caption_text(caption_path: Union[str, Path]) -> Generator:
    """Return all text from each caption of a caption file."""
    if str(caption_path).endswith('vtt'):
        # VTT
        for caption in webvtt.read(caption_path):
            text = str(caption.text).strip()
            yield text
    else:
        # Finally, try SRT
        with open(caption_path, 'rt') as fh:
            contents = fh.read()
            for subtitle in srt.parse(contents):
                if any(subtitle.content):
                    yield subtitle.content


def get_unique_caption_lines(caption_path: Union[str, Path]) -> Generator:
    """Return all unique lines from each caption of a caption file."""
    last_line = None
    for text in get_caption_text(caption_path):
        for line in text.split('\n'):
            if line and line != last_line:
                last_line = line
                yield line


def read_captions(caption_path: Path):
    """Parse video captions from the video's captions file."""
    try:
        lines = get_unique_caption_lines(str(caption_path))
        block = '\n'.join(lines)
        return block
    except UnicodeDecodeError as e:
        # Failed to decode the caption file
        # TODO handle this error
        pass
    except webvtt.errors.MalformedFileError as e:
        # File format is broken
        pass
    except webvtt.errors.MalformedCaptionError as e:
        # Captions form is broken somehow
        pass

    logger.debug(f'Failed to parse caption file {caption_path}')


def extract_captions(path: pathlib.Path) -> str | None:
    """Extract captions that are embedded in a video file."""
    with tempfile.TemporaryDirectory() as directory:
        directory = pathlib.Path(directory)
        file_path = directory / 'captions.vtt'

        if file_path.exists():
            raise FileNotFoundError(f'Cannot not extract captions when file already exists {path}')

        cmd = (FFMPEG_BIN, '-i', str(path.absolute()), file_path)
        try:
            subprocess.check_call(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except subprocess.SubprocessError:
            logger.debug(f'Unable to extract subtitles {path}')
            return ''
        if file_path.stat().st_size > 0:
            captions = read_captions(file_path)
            return captions

    # No captions could be extracted.
    return None
