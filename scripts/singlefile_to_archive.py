#!/usr/bin/env python3
"""Extracts Readability, screenshot, etc. from a Singlefile."""
import argparse
import json
import logging
import pathlib
import subprocess
import sys
import tempfile

from modules.archive import lib as archive_lib
from wrolpi.cmd import READABILITY_BIN
from wrolpi.common import html_screenshot, format_html_string, logger, format_html_file

logger = logger.getChild('singlefile_to_archive')


def do_readability(html: bytes, url: str) -> dict:
    """Extract the readability dict from the provided HTML."""
    with tempfile.NamedTemporaryFile('wb', suffix='.html') as fh:
        fh.write(html)

        cmd = (READABILITY_BIN, fh.name, url)
        output = subprocess.check_output(cmd, timeout=60)

    readability = json.loads(output)
    return readability


def singlefile_to_archive_files(singlefile: pathlib.Path):
    """Extract Readability files and Screenshot file next to the provided Singlefile."""
    contents = singlefile.read_bytes()

    format_html_file(singlefile)

    readability_html_path = singlefile.with_suffix('.readability.html')
    readability_json_path = singlefile.with_suffix('.readability.json')
    readability_text_path = singlefile.with_suffix('.readability.txt')

    # Only extract Readability if any of the files are missing.
    readability = dict()
    if not readability_html_path.is_file() or not readability_text_path.is_file() or not readability_json_path.is_file():
        url = archive_lib.get_url_from_singlefile(contents)
        try:
            readability = do_readability(contents, url)
        except Exception as e:
            logger.error(f'Failed to run readability', exc_info=e)

    # The real Readability the user wants.
    readability_html = readability.pop('content', None)
    if readability and not readability_html_path.is_file() and readability_html:
        logger.info(f'Writing readability html: {readability_html_path}')
        try:
            readability_html = format_html_string(readability_html)
            readability_html_path.write_text(readability_html)
        except Exception as e:
            logger.error(f'Failed to extract readability: {singlefile}', exc_info=e)

    # The text from within the Readability, used for searching.
    readability_text = readability.pop('textContent', None)
    if readability and not readability_text_path.is_file() and readability_text:
        logger.info(f'Writing readability txt: {readability_text_path}')
        readability_text_path.write_text(readability_text)

    # Write the JSON last now that content/textContent have been removed.
    keys = set(json.loads(readability_json_path.read_text()).keys()) if readability_json_path.is_file() else None
    if readability and (not readability_json_path.is_file() or keys == {'url'}):
        logger.info(f'Writing readability json: {readability_json_path}')
        try:
            with readability_json_path.open('wt') as fh:
                fh.write(json.dumps(readability, indent=2))
        except Exception as e:
            logger.error(f'Failed to write Readability json: {singlefile}', exc_info=e)

    # Only generate a screenshot if the file is missing.
    screenshot_path = singlefile.with_suffix('.png')
    if not screenshot_path.is_file():
        logger.info(f'Writing screenshot: {screenshot_path}')
        try:
            screenshot = html_screenshot(contents)
            screenshot_path.write_bytes(screenshot)
        except Exception as e:
            logger.error(f'Failed to create screenshot: {singlefile}', exc_info=e)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('files', nargs='*', default=['-'])
    parser.add_argument('-v', action='count', default=0)
    args = parser.parse_args()

    if args.v == 0:
        logger.setLevel(logging.WARNING)
    elif args.v == 1:
        logger.setLevel(logging.INFO)
    elif args.v >= 2:
        logger.setLevel(logging.DEBUG)
        logger.debug(f'Debug logging')

    if not READABILITY_BIN:
        print(f'Cannot find "readability-extractor".  Install it.')
        sys.exit(1)

    if args.files == ['-', ]:
        # Read list of files from stdin, separated by newlines.
        print('Reading list of files from stdin', file=sys.stderr)
        files = [pathlib.Path(i.strip()) for i in sys.stdin.readlines()]
    else:
        files = [pathlib.Path(i) for i in args.files]

    non_existent_files = [i for i in files if not i.is_file()]
    if non_existent_files:
        for i in non_existent_files:
            print(f'File does not exist: {i}')
        sys.exit(1)

    invalid_files = [i for i in files if not archive_lib.is_singlefile_file(i)]
    if invalid_files:
        for i in invalid_files:
            print(f'File is not a singlefile: {i}')
        sys.exit(1)

    for file in files:
        singlefile_to_archive_files(file)
        print(f'Finished {file}')
