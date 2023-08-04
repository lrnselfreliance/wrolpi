#! /usr/bin/env python3
import argparse
import logging
import pathlib
import subprocess
import sys
from typing import Generator

logger = logging.getLogger()
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
logger.addHandler(handler)


def walk(path: pathlib.Path) -> Generator[pathlib.Path, None, None]:
    """Recursively walk a directory structure yielding all files and directories."""
    if not path.is_dir():
        raise ValueError('Can only walk a directory.')

    for path in path.iterdir():
        yield path
        if path.is_dir():
            yield from walk(path)


def find_srt_files(directory: pathlib.Path) -> pathlib.Path:
    for path in walk(directory):
        if path.is_file() and path.suffix == '.srt':
            yield path


def convert_srt_to_vtt(srt_file: pathlib.Path, ask_delete: bool = True, throw: bool = True):
    vtt_file = srt_file.with_suffix('.vtt')
    if vtt_file.exists() and vtt_file.stat().st_size:
        if ask_delete:
            to_delete = input(f'VTT file ({vtt_file.name}) already exists, delete ({srt_file.name}) SRT? (y/N)')
            if to_delete != 'y':
                return
        srt_file.unlink()
        logger.debug(f'Deleted old: {srt_file}')
    else:
        # VTT does not yet exist, or is empty.
        if vtt_file.is_file():
            vtt_file.unlink()

        # Convert SRT to VTT.
        cmd = ('ffmpeg', '-i', str(srt_file), str(vtt_file))
        try:
            subprocess.check_call(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            logger.info(f'Converted: {repr(srt_file.name)}  ->  {repr(vtt_file.name)}')
        except subprocess.CalledProcessError as e:
            logger.error(f'Failed to convert {srt_file} to {vtt_file}', exc_info=e)
            if throw:
                raise

        if not vtt_file.is_file():
            print(f'VTT file {repr(vtt_file)} was not created!', file=sys.stderr)
            sys.exit(2)
        if not vtt_file.stat().st_size:
            print(f'VTT file {repr(vtt_file)} is empty!', file=sys.stderr)
            sys.exit(3)

        # Only delete SRT if the VTT was created.
        srt_file.unlink()
        logger.debug(f'Deleted: {srt_file}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=pathlib.Path,
                        help='The directory which contains SRT files to convert.')
    parser.add_argument('-d', '--delete', default=False, action='store_true',
                        help='Delete duplicate SRT files without prompting.')
    parser.add_argument('-i', '--ignore-errors', default=False, action='store_true',
                        help='Ignore errors and continue converting.')
    parser.add_argument('-v', action='count')
    args = parser.parse_args()

    if args.v == 0:
        logger.setLevel(logging.WARNING)
    elif args.v == 1:
        logger.setLevel(logging.INFO)
    elif args.v >= 2:
        logger.setLevel(logging.DEBUG)
        logger.debug(f'Debug logging')

    directory_: pathlib.Path = args.directory

    if not directory_.is_dir():
        print(f'{directory_} is not a directory')
        sys.exit(1)

    for srt_file_ in find_srt_files(directory_):
        convert_srt_to_vtt(srt_file_, ask_delete=not args.delete, throw=not args.ignore_errors)
