import asyncio
import base64
import gzip
import json
import pathlib
import re
from itertools import groupby
from typing import Iterator
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from modules.archive.models import URL, Domain, Archive
from wrolpi.common import get_media_directory, logger, chunks
from wrolpi.dates import now, strptime_ms, strftime_ms
from wrolpi.db import get_db_session, get_db_curs
from wrolpi.errors import InvalidDomain, UnknownURL, PendingArchive, InvalidArchive

logger = logger.getChild(__name__)

ARCHIVE_SERVICE = 'http://archive:8080'


def get_archive_directory() -> pathlib.Path:
    return get_media_directory() / 'archive'


def extract_domain(url):
    """
    Extract the domain from a URL.  Remove leading www.

    >>> extract_domain('https://www.example.com/foo')
    'example.com'
    """
    parsed = urlparse(url)
    domain = parsed.netloc
    if domain.startswith('www.'):
        # Remove leading www.
        domain = domain[4:]
    return domain


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
    dt = strftime_ms(now())

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


ARCHIVE_TIMEOUT = 10 * 60  # Wait at most 10 minutes for response.


def request_archive(url: str):
    """
    Send a request to the archive service to archive the URL.
    """
    data = {'url': url}
    try:
        resp = requests.post(f'{ARCHIVE_SERVICE}/json', json=data, timeout=ARCHIVE_TIMEOUT)
    except Exception as e:
        logger.error('Error when requesting archive', exc_info=e)
        raise
    singlefile = resp.json()['singlefile']
    readability = resp.json()['readability']
    screenshot = resp.json()['screenshot']

    if not (screenshot or singlefile or readability):
        raise Exception('singlefile response was empty!')

    if not singlefile:
        logger.info(f'Failed to get singlefile for {url=}')
    else:
        # Decode and decompress.
        singlefile = base64.b64decode(singlefile)
        singlefile = gzip.decompress(singlefile)

    if not readability:
        logger.info(f'Failed to get readability for {url=}')

    if not screenshot:
        logger.info(f'Failed to get screenshot for {url=}')
    else:
        # Decode and decompress.
        screenshot = base64.b64decode(screenshot)
        screenshot = gzip.decompress(screenshot)

    return singlefile, readability, screenshot


def is_pending_archive(url: str) -> bool:
    with get_db_session() as session:
        url = session.query(URL).filter_by(url=url).one_or_none()
        if url and url.latest.status == 'pending':
            return True
    return False


def new_archive(url: str, sync: bool = False):
    """
    Request archiving of the provided URL.  Store the returned files in their domain's directory.

    :param url: The URL to archive.
    :param sync: Perform the archiving process synchronously for testing.
    """
    # Check that the archive files are available.
    get_new_archive_files(url)

    if is_pending_archive(url):
        raise PendingArchive()

    with get_db_session(commit=True) as session:
        domain, url_ = get_or_create_domain_and_url(session, url)

        archive = Archive(
            url_id=url_.id,
            domain_id=domain.id,
            status='pending',
            archive_datetime=now(),
        )
        session.add(archive)
        session.flush()
        archive_id = archive.id

        url_.latest_id = archive_id
        url_.latest_datetime = now()

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
    try:
        singlefile, readability, screenshot = request_archive(url)

        singlefile_path, readability_path, readability_txt_path, readability_json_path, screenshot_path = \
            get_new_archive_files(url)

        # Store the single-file HTML in it's own file.
        with singlefile_path.open('wt') as fh:
            fh.write(singlefile)
        if screenshot:
            with screenshot_path.open('wb') as fh:
                fh.write(screenshot)
        else:
            screenshot_path = None

        # Store the Readability into separate files.  This allows the user to view text-only or html articles.
        title = None
        if readability:
            title = readability.get('title')

            # Write the readability parts to their own files.  Write what is left after pops to the JSON file.
            with readability_path.open('wt') as fh:
                fh.write(readability.pop('content'))
            with readability_txt_path.open('wt') as fh:
                fh.write(readability.pop('textContent'))
        else:
            readability_path = readability_txt_path = None

        # Always write a JSON file that contains at least the URL.
        readability = readability or {}
        # Use the Readability title, or try and extract one from singlefile.
        if not title and singlefile:
            title = get_title_from_html(singlefile, url=url)
            readability['title'] = title
        readability['url'] = url
        with readability_json_path.open('wt') as fh:
            fh.write(json.dumps(readability))

        with get_db_session(commit=True) as session:
            archive = session.query(Archive).filter_by(id=archive_id).one()
            archive.status = 'complete'
            archive.archive_datetime = now()
            archive.title = title
            archive.singlefile_path = singlefile_path
            archive.readability_path = readability_path
            archive.readability_json_path = readability_json_path
            archive.readability_txt_path = readability_txt_path
            archive.screenshot_path = screenshot_path
            # Update the latest for easy viewing.
            archive.url.latest_id = archive.id
            archive.url.latest_datetime = archive.archive_datetime

        return archive
    except Exception:
        with get_db_session(commit=True) as session:
            archive = session.query(Archive).filter_by(id=archive_id).one()
            archive.status = 'failed'
        raise


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


def get_title_from_html(html: str, url: str = None) -> str:
    """
    Try and get the title from the
    """
    soup = BeautifulSoup(html, features='html.parser')
    try:
        return soup.title.string
    except Exception:  # noqa
        logger.info(f'Unable to extract title {url}')


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
            urls = sorted(urls, key=lambda i: i.latest_datetime)[::-1]
        else:
            urls = session.query(URL) \
                .order_by(URL.latest_datetime.desc()) \
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


def delete_url(url_id: int):
    """
    Delete a URL record, all it's Archives and files.
    """
    with get_db_session() as session:
        url: URL = session.query(URL).filter_by(id=url_id).one_or_none()
        if not url:
            raise UnknownURL(f'Unknown url with id: {url_id}')

        # Delete any files associated with this URL.
        for archive in url.archives:
            archive.unlink()

    with get_db_session(commit=True) as session:
        session.query(URL).filter_by(id=url_id).delete()


def group_archive_files(files: Iterator[pathlib.Path]) -> groupby:
    """
    Group archive files by their timestamp.
    """
    # groupby requires the files to be sorted.
    files = sorted(files)
    # Group archive files by their datetime at the beginning of the file.
    groups = groupby(files, key=lambda i: i.name[:26])
    for dt, files in groups:
        try:
            dt = strptime_ms(dt)
        except ValueError:
            logger.info(f'Ignoring invalid archives of {dt=}')
            continue

        # Sort the files into their respective slots.
        singlefile_path = readability_path = readability_txt_path = readability_json_path = screenshot_path = None
        file = None
        for file in files:
            if file.name.endswith('-readability.html'):
                readability_path = file
            elif file.name.endswith('.html'):
                singlefile_path = file
            elif file.name.endswith('.png') or file.name.endswith('.jpg') or file.name.endswith('.jpeg'):
                screenshot_path = file
            elif file.name.endswith('-readability.json'):
                readability_json_path = file
            elif file.name.endswith('-readability.txt'):
                readability_txt_path = file

        if not singlefile_path:
            logger.warning(f'Archive does not have a singlefile html!  Ignoring. {file}')
            continue
        if not readability_json_path:
            logger.warning(f'Archive does not have a json file!  Ignoring. {file}')
            continue

        yield dt, (singlefile_path, readability_path, readability_txt_path, readability_json_path, screenshot_path)


ARCHIVE_MATCHER = re.compile(r'\d{4}-\d\d-\d\d (\d\d:){2}\d\d\.\d{6}.*$')
ARCHIVE_SUFFIXES = {'.txt', '.html', '.json', '.png', '.jpg', '.jpeg'}


def is_archive_file(path: pathlib.Path) -> bool:
    """
    Archive files are expected to start with the following: %Y-%m-%d %H:%M:%S.%f
    they must have one of the following suffixes: .txt, .html, .json, .png, .jpg, .jpeg
    """
    return path.is_file() and path.suffix.lower() in ARCHIVE_SUFFIXES and bool(ARCHIVE_MATCHER.match(path.name))


def _refresh_archives():
    """
    Search the Archives directory for archive files, update the database if new files are found.
    """
    archive_directory = get_archive_directory()
    for domain_directory in filter(lambda i: i.is_dir(), archive_directory.iterdir()):
        logger.debug(f'Refreshing directory: {domain_directory}')
        archives_files = filter(is_archive_file, domain_directory.iterdir())
        archive_groups = group_archive_files(archives_files)
        archive_count = 0
        for chunk in chunks(archive_groups, 20):
            archive_count += 1
            with get_db_session(commit=True) as session:
                for dt, files in chunk:
                    print('_refresh_archives', dt)
                    upsert_archive(dt, files, session)

        if archive_count:
            logger.info(f'Inserted/updated {archive_count} archives')

    cleanup_domains_urls()


def cleanup_domains_urls():
    """
    Delete any URLs/Domains without Archives.
    """
    with get_db_curs(commit=True) as curs:
        stmt = '''
            DELETE FROM url WHERE id NOT IN (
                select distinct url_id from archive
            ) RETURNING url.id
        '''
        curs.execute(stmt)
        urls = list(map(dict, curs.fetchall()))
        stmt = '''
            DELETE FROM domains WHERE id NOT IN (
                select distinct domain_id from url
            ) RETURNING domains.id
        '''
        curs.execute(stmt)
        domains = list(map(dict, curs.fetchall()))
        logger.info(f'Deleted {len(urls)} URLS and {len(domains)} Domains')


async def refresh_archives():
    _refresh_archives()


def upsert_archive(dt: str, files, session: Session):
    """
    Get or create an Archive and it's URL/Domain.  If it already exists, update it with these new files.
    """
    singlefile_path, readability_path, readability_txt_path, readability_json_path, screenshot_path = files
    # Extract the URL from the JSON.  Fail if this is not possible.
    try:
        with readability_json_path.open() as fh:
            json_contents = json.load(fh)
            url = json_contents['url']
    except Exception as e:
        raise InvalidArchive() from e

    domain, url_ = get_or_create_domain_and_url(session, url)
    logger.debug(f'Upsert url={url_.url}')
    # Get the existing Archive, or create a new one.
    archive = session.query(Archive).filter_by(singlefile_path=singlefile_path).one_or_none()
    if not archive:
        # No archive matches this singlefile_path, create a new one.
        archive = Archive(
            url_id=url_.id,
            domain_id=domain.id,
        )
        session.add(archive)
        session.flush()

    # Update the archive with the files that we have.
    archive.status = 'complete',
    archive.archive_datetime = dt
    archive.singlefile_path = singlefile_path
    archive.readability_path = readability_path
    archive.readability_txt_path = readability_txt_path
    archive.readability_json_path = readability_json_path
    archive.screenshot_path = screenshot_path
    archive_id = archive.id

    if not url_.latest_datetime or url_.latest_datetime < dt:
        url_.latest_id = archive_id
        url_.latest_datetime = archive.archive_datetime


def get_domains():
    with get_db_curs() as curs:
        stmt = '''
            SELECT domains.domain AS domain, COUNT(u.id) AS url_count
            FROM domains
            LEFT JOIN url u on domains.id = u.domain_id
            GROUP BY domains.domain
            ORDER BY domains.domain
        '''
        curs.execute(stmt)
        domains = list(map(dict, curs.fetchall()))
        return domains
