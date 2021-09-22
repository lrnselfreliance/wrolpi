import contextlib
import json
import pathlib
from functools import lru_cache
from typing import Tuple
from urllib.parse import urlparse

import requests

from wrolpi.common import get_media_directory, logger, now
from wrolpi.vars import DATETIME_FORMAT_MS

logger = logger.getChild(__name__)

ARCHIVE_SERVICE = 'http://archive:8080'


@lru_cache(maxsize=1)
def get_archive_directory() -> pathlib.Path:
    return get_media_directory() / 'archive'


def get_domain(url):
    parsed = urlparse(url)
    return parsed.netloc


def get_domain_directory(url: str) -> pathlib.Path:
    """
    Get the archive directory for a particular domain.
    """
    domain = get_domain(url)
    directory = get_archive_directory() / domain
    if directory.is_dir():
        return directory
    elif directory.is_file():
        raise FileNotFoundError(f'Domain directory {directory} is already a file')

    directory.mkdir()
    return directory


def get_new_archive_file(url: str) -> Tuple[pathlib.Path, pathlib.Path, pathlib.Path, pathlib.Path]:
    directory = get_domain_directory(url)
    dt = now().strftime(DATETIME_FORMAT_MS)
    singlefile = directory / f'{dt}-singlefile.html'
    if singlefile.exists():
        raise FileExistsError(f'Cannot get new archive file, it already exists: {singlefile}')

    readability = directory / f'{dt}-readability.html'
    if readability.exists():
        raise FileExistsError(f'Cannot get new archive file, it already exists: {readability}')

    readability_json = directory / f'{dt}-readability.json'
    if readability_json.exists():
        raise FileExistsError(f'Cannot get new archive file, it already exists: {readability_json}')

    readability_txt = directory / f'{dt}-readability.txt'
    if readability_txt.exists():
        raise FileExistsError(f'Cannot get new archive file, it already exists: {readability_txt}')

    # Yield the file path because it does not exist
    return singlefile, readability, readability_json, readability_txt


def request_archive(url: str):
    """
    Send a request to the archive service to archive the URL.
    """
    data = {'url': url}
    try:
        resp = requests.post(f'{ARCHIVE_SERVICE}/json', json=data)
    except Exception as e:
        logger.error('Error when requesting single-file', exc_info=e)
        raise
    singlefile = resp.json()['singlefile'].encode()
    readability = resp.json()['readability']
    return singlefile, readability


def new_archive(url: str):
    singlefile_path, readability_path, readability_json_path, readability_txt = get_new_archive_file(url)

    singlefile, readability = request_archive(url)

    # Store the single-file HTML in it's own file.
    with singlefile_path.open('wb') as fh:
        fh.write(singlefile)

    # Store the Readability into separate files.  This allows the user to view text-only or html articles.
    with readability_path.open('wb') as fh:
        fh.write(readability.pop('content').encode())
    with readability_txt.open('wb') as fh:
        fh.write(readability.pop('textContent').encode())
    with readability_json_path.open('wt') as fh:
        fh.write(json.dumps(readability))
