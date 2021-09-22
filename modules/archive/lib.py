import base64
import pathlib
from functools import lru_cache
from urllib.parse import urlparse

import requests

from modules.archive.models import URL, Domain, Archive
from wrolpi.common import get_media_directory, logger, now
from wrolpi.db import get_db_session
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


def get_new_archive_files(url: str):
    """
    Create a list of archive files using a shared name schema.  Raise an error if any of them exist.
    """
    directory = get_domain_directory(url)
    dt = now().strftime(DATETIME_FORMAT_MS)

    singlefile = directory / f'{dt}.html'
    readability = directory / f'{dt}-readability.html'
    readability_txt = directory / f'{dt}-readability.txt'
    screenshot_png = directory / f'{dt}.png'

    ret = (singlefile, readability, readability_txt, screenshot_png)

    for path in ret:
        if path.exists():
            raise FileExistsError(f'New archive file already exists: {path}')

    return ret


def request_archive(url: str):
    """
    Send a request to the archive service to archive the URL.
    """
    data = {'url': url}
    try:
        resp = requests.post(f'{ARCHIVE_SERVICE}/json', json=data)
    except Exception as e:
        logger.error('Error when requesting archive', exc_info=e)
        raise
    singlefile = resp.json()['singlefile'].encode()
    readability = resp.json()['readability']
    screenshot = resp.json()['screenshot']
    if screenshot:
        screenshot = base64.b64decode(screenshot)
    return singlefile, readability, screenshot


def new_archive(url: str):
    """
    Request archiving of the provided URL.  Store the returned files in their domain's directory.
    """
    singlefile_path, readability_path, readability_txt, screenshot_path = \
        get_new_archive_files(url)

    singlefile, readability, screenshot = request_archive(url)

    # Store the single-file HTML in it's own file.
    with singlefile_path.open('wb') as fh:
        fh.write(singlefile)

    if screenshot:
        with screenshot_path.open('wb') as fh:
            fh.write(screenshot)

    # Store the Readability into separate files.  This allows the user to view text-only or html articles.
    title = None
    if readability:
        with readability_path.open('wb') as fh:
            fh.write(readability.pop('content').encode())
        with readability_txt.open('wb') as fh:
            fh.write(readability.pop('textContent').encode())

        title = readability.get('title')

    with get_db_session(commit=True) as session:
        # Get/create the Domain for this archive.
        domain_ = get_domain(url)
        domain = session.query(Domain).filter_by(domain=domain_).one_or_none()
        if not domain:
            domain = Domain(domain=domain_, directory=str(get_domain_directory(url)))
            session.add(domain)
            session.flush()

        url_ = session.query(URL).filter_by(url=url).one_or_none()
        if not url_:
            url_ = URL(url=url, domain_id=domain.id)
            session.add(url_)
            session.flush()

        archive = Archive(
            singlefile_path=singlefile_path,
            readability_path=readability_path if readability_path.is_file() else None,
            readability_txt_path=readability_txt if readability_txt.is_file() else None,
            screenshot_path=screenshot_path if screenshot_path.is_file() else None,
            title=title,
            archive_datetime=now(),
            url_id=url_.id,
            domain_id=domain.id,
        )
        session.add(archive)
        session.flush()

        # Update the latest for easy viewing.
        url_.latest = archive.id
        url_.latest_datetime = archive.archive_datetime

        return archive
