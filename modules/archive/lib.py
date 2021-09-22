import contextlib
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
    readability = resp.json()['readability'].encode()
    return singlefile, readability


@contextlib.contextmanager
def get_new_archive_file(url: str) -> Tuple[pathlib.Path, pathlib.Path]:
    directory = get_domain_directory(url)
    singlefile = directory / f'{now().strftime(DATETIME_FORMAT_MS)}-singlefile.html'
    if singlefile.exists():
        raise FileExistsError(f'Cannot get new archive file, it already exists: {singlefile}')

    readability = directory / f'{now().strftime(DATETIME_FORMAT_MS)}-readability.html'
    if readability.exists():
        raise FileExistsError(f'Cannot get new archive file, it already exists: {readability}')

    # Yield the file path because it does not exist
    yield singlefile, readability


def new_archive(url: str):
    with get_new_archive_file(url) as (singlefile_path, readability_path):
        singlefile, readability = request_archive(url)
        with singlefile_path.open('wb') as fh:
            fh.write(singlefile)
        with readability_path.open('wb') as fh:
            fh.write(readability)
