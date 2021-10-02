import asyncio
import base64
import json
import pathlib
from functools import lru_cache
from urllib.parse import urlparse

import requests

from modules.archive.models import URL, Domain, Archive
from wrolpi.common import get_media_directory, logger, now
from wrolpi.db import get_db_session, get_db_curs
from wrolpi.errors import InvalidDomain
from wrolpi.vars import DATETIME_FORMAT_MS

logger = logger.getChild(__name__)

ARCHIVE_SERVICE = 'http://archive:8080'


@lru_cache(maxsize=1)
def get_archive_directory() -> pathlib.Path:
    return get_media_directory() / 'archive'


def extract_domain(url):
    parsed = urlparse(url)
    return parsed.netloc


def get_domain_directory(url: str) -> pathlib.Path:
    """
    Get the archive directory for a particular domain.
    """
    domain = extract_domain(url)
    directory = get_archive_directory() / domain
    if directory.is_dir():
        return directory
    elif directory.exists():
        raise FileNotFoundError(f'Domain directory {directory} is already a file')

    directory.mkdir()
    return directory


def get_new_archive_files(url: str):
    """
    Create a list of archive files using a shared name schema.  Raise an error if any of them exist.
    """
    directory = get_domain_directory(url)
    dt = now().strftime(DATETIME_FORMAT_MS)

    singlefile_path = directory / f'{dt}.html'
    readability_path = directory / f'{dt}-readability.html'
    readability_txt_path = directory / f'{dt}-readability.txt'
    readability_json_path = directory / f'{dt}-readability.json'
    screenshot_path = directory / f'{dt}.png'

    ret = (singlefile_path, readability_path, readability_txt_path, readability_json_path, screenshot_path)

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
    singlefile = resp.json()['singlefile']
    readability = resp.json()['readability']
    screenshot = resp.json()['screenshot']

    if not screenshot:
        raise Exception('singlefile response was empty!')

    if screenshot:
        screenshot = base64.b64decode(screenshot)
    return singlefile, readability, screenshot


def new_archive(url: str, sync: bool = False):
    """
    Request archiving of the provided URL.  Store the returned files in their domain's directory.

    :param url: The URL to archive.
    :param sync: Perform the archiving process synchronously for testing.
    """
    # Check that the archive files are available.
    get_new_archive_files(url)

    with get_db_session(commit=True) as session:
        domain, url_ = get_or_create_domain_and_url(session, url)

        archive = Archive(
            url_id=url_.id,
            domain_id=domain.id,
        )
        session.add(archive)
        session.flush()
        archive_id = archive.id

    if sync:
        return _do_archive(url, archive_id)
    else:
        # Run the real archive process in the future.
        asyncio.ensure_future(do_archive(url, archive_id))

    return archive


def _do_archive(url: str, archive_id: int):
    """
    Perform the real archive request to the archiving service.  Store the resulting data into files.  Update the Archive
    in the DB.
    """
    singlefile, readability, screenshot = request_archive(url)

    singlefile_path, readability_path, readability_txt_path, readability_json_path, screenshot_path = \
        get_new_archive_files(url)

    # Store the single-file HTML in it's own file.
    with singlefile_path.open('wt') as fh:
        fh.write(singlefile)
    if screenshot:
        with screenshot_path.open('wb') as fh:
            fh.write(screenshot)

    # Store the Readability into separate files.  This allows the user to view text-only or html articles.
    title = None
    if readability:
        title = readability.get('title')

        # Write the readability parts to their own files.  Write what is left after pops to the JSON file.
        with readability_path.open('wt') as fh:
            fh.write(readability.pop('content'))
        with readability_txt_path.open('wt') as fh:
            fh.write(readability.pop('textContent'))
        with readability_json_path.open('wt') as fh:
            fh.write(json.dumps(readability))

    with get_db_session(commit=True) as session:
        archive = session.query(Archive).filter_by(id=archive_id).one()
        archive.archive_datetime = now()
        archive.title = title
        archive.singlefile_path = singlefile_path
        archive.readability_path = readability_path if readability_path.is_file() else None
        archive.readability_json_path = readability_json_path if readability_json_path.is_file() else None
        archive.readability_txt_path = readability_txt_path if readability_txt_path.is_file() else None
        archive.screenshot_path = screenshot_path if screenshot_path.is_file() else None
        # Update the latest for easy viewing.
        archive.url.latest_id = archive.id
        archive.url.latest_datetime = archive.archive_datetime

    return archive


async def do_archive(url: str, archive_id: int):
    _do_archive(url, archive_id)


def get_or_create_domain_and_url(session, url):
    """
    Get/create the Domain for this archive.
    """
    domain_ = extract_domain(url)
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
    return domain, url_


def get_domain(session, domain: str) -> Domain:
    domain_ = session.query(Domain).filter_by(domain=domain).one_or_none()
    if not domain_:
        raise InvalidDomain(f'Invalid domain: {domain}')
    return domain_


def get_urls(limit: int = 20, offset: int = 0, domain: str = ''):
    with get_db_session() as session:
        if domain:
            domain_ = get_domain(session, domain)
            urls = domain_.urls[offset:offset + limit]
        else:
            urls = session.query(URL) \
                .order_by(URL.latest_datetime) \
                .limit(limit) \
                .offset(offset) \
                .all()
        urls = [i.dict() for i in urls]
        return urls


def get_url_count(domain: str = '') -> int:
    """
    Get count of all URLs.  Or, get count of all attached to a specific domain string.
    """
    with get_db_session() as session:
        domain_id = None
        if domain:
            domain_id = get_domain(session, domain).id

    with get_db_curs() as curs:
        stmt = 'SELECT COUNT(*) FROM url'
        params = {}
        if domain_id:
            stmt = f'{stmt} WHERE domain_id = %(domain_id)s'
            params['domain_id'] = domain_id
        curs.execute(stmt, params)
        count = int(curs.fetchone()[0])
        return count
