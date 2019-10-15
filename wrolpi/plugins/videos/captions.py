#! /usr/bin/env python3
from typing import Generator

import webvtt


def get_caption_text(vtt_path: str) -> Generator:
    for caption in webvtt.read(vtt_path):
        text = str(caption.text).strip()
        yield text


def get_unique_caption_lines(vtt_path: str) -> Generator:
    last_line = None
    for text in get_caption_text(vtt_path):
        for line in text.split('\n'):
            if line and line != last_line:
                last_line = line
                yield line

