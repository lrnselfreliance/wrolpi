#! /usr/bin/env python3
import pathlib
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Generator, List, Optional, Union

import srt
import webvtt

from wrolpi.cmd import FFMPEG_BIN
from wrolpi.common import logger

__all__ = ['read_captions', 'read_captions_with_timestamps', 'extract_captions',
           'strip_youtube_caption_positioning']

# YouTube auto-generated captions (downloaded via yt-dlp) stamp every cue's timing line with
# `align:start position:0%`, which pins the on-screen text to the bottom-left of the player and makes it hard
# to read.  This matches only that exact signature on a cue timing line so we never touch a deliberately
# positioned cue.  The `<c>` word-timing tags in the cue text are left untouched.
YOUTUBE_CUE_SETTINGS = re.compile(
    r'^(\d{2}:\d{2}:\d{2}\.\d{3} --> \d{2}:\d{2}:\d{2}\.\d{3}) align:start position:0%[ \t]*$',
    re.MULTILINE,
)


def strip_youtube_caption_positioning(caption_path: Union[str, Path]) -> bool:
    """Remove YouTube's `align:start position:0%` cue settings from a .vtt file so the browser renders the
    captions centered.  Rewrites the file in place only if something changed.

    This is intended for captions downloaded from youtube.com; the caller is responsible for that gate.

    :return: True if the file was modified.
    """
    caption_path = pathlib.Path(caption_path)
    text = caption_path.read_text()
    new_text = YOUTUBE_CUE_SETTINGS.sub(r'\1', text)
    if new_text != text:
        caption_path.write_text(new_text)
        logger.info(f'Centered YouTube captions in {caption_path}')
        return True
    return False


def _parse_vtt_timestamp(timestamp: str) -> float:
    """Parse a VTT timestamp like '00:01:05.269' to seconds as a float."""
    parts = timestamp.strip().split(':')
    if len(parts) == 3:
        hours, minutes, seconds = parts
    elif len(parts) == 2:
        hours = '0'
        minutes, seconds = parts
    else:
        return 0.0
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _parse_caption_file(caption_path: Union[str, Path]) -> List[dict]:
    """Parse a VTT or SRT file into raw caption chunks with timestamps.
    Returns a list of dicts with 'start_seconds' and 'text' keys."""
    raw_chunks = []
    caption_path = str(caption_path)
    if caption_path.endswith('vtt'):
        for caption in webvtt.read(caption_path):
            text = str(caption.text).strip()
            if text:
                start = _parse_vtt_timestamp(caption.start)
                raw_chunks.append({'start_seconds': start, 'text': text})
    else:
        with open(caption_path, 'rt') as fh:
            contents = fh.read()
            for subtitle in srt.parse(contents):
                text = subtitle.content.strip()
                if text:
                    start = subtitle.start.total_seconds()
                    raw_chunks.append({'start_seconds': start, 'text': text})
    return raw_chunks


def _deduplicate_caption_chunks(raw_chunks: List[dict]) -> List[dict]:
    """Deduplicate caption chunks by extracting only new lines from each chunk.

    YouTube auto-captions produce overlapping chunks where each chunk repeats lines from the previous one
    plus new content.  This extracts only the new lines and assigns the chunk's start timestamp."""
    chunks = []
    last_lines = []
    for chunk in raw_chunks:
        lines = [line for line in chunk['text'].split('\n') if line.strip()]
        new_lines = [line for line in lines if line not in last_lines]
        if new_lines:
            text = '\n'.join(new_lines)
            if not chunks or text != chunks[-1]['text']:
                chunks.append({'start_seconds': chunk['start_seconds'], 'text': text})
        last_lines = lines
    return chunks


def get_caption_text(caption_path: Union[str, Path]) -> Generator:
    """Return all text from each caption of a caption file."""
    for chunk in _parse_caption_file(caption_path):
        yield chunk['text']


def get_unique_caption_lines(caption_path: Union[str, Path]) -> Generator:
    """Return all unique lines from each caption of a caption file."""
    last_line = None
    for text in get_caption_text(caption_path):
        for line in text.split('\n'):
            if line and line != last_line:
                last_line = line
                yield line


def read_captions(caption_path: Path):
    """Parse video captions from the video's captions file.  Returns deduplicated caption text as a string."""
    try:
        lines = get_unique_caption_lines(str(caption_path))
        block = '\n'.join(lines)
        return block
    except UnicodeDecodeError:
        pass
    except webvtt.errors.MalformedFileError:
        pass
    except webvtt.errors.MalformedCaptionError:
        pass
    logger.debug(f'Failed to parse caption file {caption_path}')


def read_captions_with_timestamps(caption_path: Path) -> Optional[List[dict]]:
    """Parse video captions preserving timestamps. Returns a list of dicts with 'start_seconds' and 'text' keys.
    Overlapping and duplicate lines are deduplicated."""
    try:
        raw_chunks = _parse_caption_file(caption_path)
        chunks = _deduplicate_caption_chunks(raw_chunks)
        return chunks if chunks else None
    except UnicodeDecodeError:
        pass
    except webvtt.errors.MalformedFileError:
        pass
    except webvtt.errors.MalformedCaptionError:
        pass
    logger.debug(f'Failed to parse caption file {caption_path}')
    return None


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
