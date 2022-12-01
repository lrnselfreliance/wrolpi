#! /usr/bin/env python3
"""
Transcribes video files, then creates an SRT file next to each.

# ls
video1.mp4
video2.mp4

# generate_subtitles.py -vv --language en --model small.en video1.mp4 video2.mp4

# ls
video1.mp4
video1.en.srt
video2.mp4
video2.en.srt
"""
import argparse
import logging
import pathlib
import sys
from typing import List

try:
    # This is not in the requirements.txt because it is not required and does not work on a Raspberry Pi.
    import whisper
except ImportError:
    whisper = None

__all__ = ['video_speech_to_srt_file', 'video_speech_to_srt']

logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
logger.addHandler(handler)

MINUTE = 60
HOUR = MINUTE * 60


def format_timestamp(seconds: float):
    """Convert seconds to the expected SRT timestamp format."""
    seconds, milliseconds = divmod(seconds, 1)
    hours, seconds = divmod(seconds, HOUR)
    minutes, seconds = divmod(seconds, MINUTE)

    milliseconds *= 1000
    hours, minutes, seconds, milliseconds = int(hours), int(minutes), int(seconds), int(milliseconds)

    timestamp = f'{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}'
    return timestamp


def video_speech_to_srt(file: pathlib.Path, model, language):
    """Transcribe a video file.  Return the text of the SRT file."""
    logger.info(f'Transcribing: {file}')
    transcription = model.transcribe(str(file), language=language)
    segments = transcription['segments']

    srt_lines = []
    for segment in segments:
        start, end, id_, text = segment['start'], segment['end'], segment['id'], segment['text']
        logger.debug(f'{file} --- {start} --> {end} {text}')
        start, end = format_timestamp(start), format_timestamp(end)
        srt_lines.append(f'{id_ + 1}\n{start} --> {end}\n{text}\n')

    return '\n'.join(srt_lines)


def video_speech_to_srt_file(video_path: pathlib.Path, srt_path: pathlib.Path, model, language: str):
    """Transcribe a video, save the resulting transcription in the SRT file."""
    srt = video_speech_to_srt(video_path, model, language)
    srt_path.write_text(srt, encoding='utf-8')


def main(video_files: List[str], model: str, language: str):
    video_files = [pathlib.Path(i) for i in video_files]

    # Check that all files are real before we do anything.
    for video_file in video_files:
        if not video_file.is_file():
            print(f'{video_file} is not a video file', file=sys.stderr)
            sys.exit(2)

    srt_suffix = f'.{language}.srt' if language else '.srt'

    logger.info(f'Loading model {model}...')
    model = whisper.load_model(model)
    logger.debug('Model loading complete.')

    for video_file in video_files:
        srt_path = video_file.with_suffix(srt_suffix)
        if srt_path.exists():
            logger.warning(f'{srt_path} already exists, skipping...')
            continue

        video_speech_to_srt_file(video_file, srt_path, model, args.language)


if __name__ == '__main__':
    parser = argparse.ArgumentParser('Transcribes video files, then creates an SRT file next to each.')
    parser.add_argument('files', nargs='+')
    parser.add_argument('--model', default='small')
    parser.add_argument('--language', default='en')
    parser.add_argument('-v', action='count', default=0)
    args = parser.parse_args()

    if whisper is None:
        print('You must install whisper.  See https://github.com/openai/whisper', file=sys.stderr)
        sys.exit(1)

    if args.v == 0:
        logger.setLevel(logging.WARNING)
    elif args.v == 1:
        logger.setLevel(logging.INFO)
    elif args.v > 1:
        logger.setLevel(logging.DEBUG)

    main(
        args.files,
        args.model,
        args.language,
    )
    sys.exit(0)
