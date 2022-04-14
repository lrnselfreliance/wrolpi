import base64
import gzip
import json
import pathlib
import re
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime
from itertools import groupby
from typing import Iterator, Optional, Tuple, List

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from sqlalchemy.orm import Session

from modules.archive.models import Domain, Archive
from wrolpi.cmd import which
from wrolpi.common import get_media_directory, logger, chunks, extract_domain, chdir, escape_file_name, walk
from wrolpi.dates import now, Seconds, local_timezone
from wrolpi.db import get_db_session, get_db_curs, get_ranked_models
from wrolpi.errors import InvalidDomain, UnknownURL, InvalidArchive
from wrolpi.vars import DOCKERIZED, PYTEST

logger = logger.getChild(__name__)

ARCHIVE_SERVICE = 'http://archive:8080'


@dataclass
class ArchiveFiles:
    """Every Archive will have some of these files."""
    singlefile: pathlib.Path = None
    readability: pathlib.Path = None
    readability_txt: pathlib.Path = None
    readability_json: pathlib.Path = None
    screenshot: pathlib.Path = None

    def __repr__(self):
        singlefile = str(self.singlefile.relative_to(get_archive_directory())) if self.singlefile else None
        readability = str(self.readability.relative_to(get_archive_directory())) if self.readability else None
        readability_txt = str(
            self.readability_txt.relative_to(get_archive_directory())) if self.readability_txt else None
        readability_json = str(
            self.readability_json.relative_to(get_archive_directory())) if self.readability_json else None
        screenshot = str(self.screenshot.relative_to(get_archive_directory())) if self.screenshot else None
        return f'<ArchiveFiles {singlefile=} {readability=} {readability_txt=} {readability_json=} {screenshot=}>'


def get_archive_directory() -> pathlib.Path:
    archive_directory = get_media_directory() / 'archive'
    if not archive_directory.is_dir():
        archive_directory.mkdir()
    return archive_directory


def get_domain_directory(url: str) -> pathlib.Path:
    """Get the archive directory for a particular domain."""
    domain = extract_domain(url)
    directory = get_archive_directory() / domain
    if directory.is_dir():
        return directory
    elif directory.exists():
        raise FileNotFoundError(f'Domain directory {directory} is already a file')

    directory.mkdir()
    return directory


def get_new_archive_files(url: str, title: Optional[str]) -> ArchiveFiles:
    """Create a list of archive files using a shared name schema.  Raise an error if any of them exist."""
    directory = get_domain_directory(url)
    # Datetime is valid in Linux and Windows.
    dt = archive_strftime(now())

    title = escape_file_name(title or 'NA')
    title = title[:50]
    prefix = f'{dt}_{title}'
    singlefile_path = directory / f'{prefix}.html'
    readability_path = directory / f'{prefix}.readability.html'
    readability_txt_path = directory / f'{prefix}.readability.txt'
    readability_json_path = directory / f'{prefix}.readability.json'
    screenshot_path = directory / f'{prefix}.png'

    paths = (singlefile_path, readability_path, readability_txt_path, readability_json_path, screenshot_path)

    for path in paths:
        if path.exists():
            raise FileExistsError(f'New archive file already exists: {path}')

    archive_files = ArchiveFiles(
        singlefile_path,
        readability_path,
        readability_txt_path,
        readability_json_path,
        screenshot_path,
    )
    return archive_files


ARCHIVE_TIMEOUT = Seconds.minute * 10  # Wait at most 10 minutes for response.


def request_archive(url: str):
    """
    Send a request to the archive service to archive the URL.
    """
    logger.info(f'Sending archive request to archive service: {url}')

    data = {'url': url}
    try:
        resp = requests.post(f'{ARCHIVE_SERVICE}/json', json=data, timeout=ARCHIVE_TIMEOUT)
    except Exception as e:
        logger.error('Error when requesting archive', exc_info=e)
        raise

    logger.debug(f'archive request status {resp.status_code=}')

    readability = resp.json()['readability']
    # Compressed base64
    singlefile = resp.json()['singlefile']
    screenshot = resp.json()['screenshot']

    if not (screenshot or singlefile or readability):
        raise Exception('singlefile response was empty!')

    if not readability:
        logger.info(f'Failed to get readability for {url=}')

    if not singlefile:
        logger.info(f'Failed to get singlefile for {url=}')
    else:
        # Decode and decompress.
        singlefile = base64.b64decode(singlefile)
        singlefile = gzip.decompress(singlefile)
        singlefile = singlefile.decode()

    if not screenshot:
        logger.info(f'Failed to get screenshot for {url=}')
    else:
        # Decode and decompress.
        screenshot = base64.b64decode(screenshot)
        screenshot = gzip.decompress(screenshot)

    return singlefile, readability, screenshot


SINGLE_FILE_PATH = which('single-file',
                         '/usr/bin/single-file',  # rpi ubuntu
                         '/usr/local/bin/single-file',  # debian
                         warn=True)
CHROMIUM = which('chromium-browser', 'chromium',
                 '/usr/bin/chromium-browser',  # rpi ubuntu
                 '/usr/bin/chromium',  # debian
                 warn=True
                 )


def local_singlefile(url: str):
    """Run the single-file executable to create an HTML file archive."""
    if not SINGLE_FILE_PATH.is_file():
        raise FileNotFoundError(f'single-file not found')

    cmd = (str(SINGLE_FILE_PATH),
           url,
           '--browser-executable-path', CHROMIUM,
           '--browser-args', '["--no-sandbox"]',
           '--dump-content')
    logger.debug(f'archive cmd: {cmd}')
    output = subprocess.check_output(cmd, timeout=60 * 3)
    logger.debug(f'done archiving for {url}')
    return output


def local_screenshot(url: str) -> bytes:
    """Take a screenshot of the URL using chromedriver."""
    logger.info(f'Screenshot: {url}')

    # Set Chromium to headless.  Use a wide window size so that screenshot will be the "desktop" version of the page.
    options = webdriver.ChromeOptions()
    options.add_argument('headless')
    options.add_argument('disable-gpu')
    options.add_argument('window-size=1280x720')

    driver = webdriver.Chrome(chrome_options=options)
    try:
        driver.get(url)
        png = driver.get_screenshot_as_png()
    except Exception as e:
        logger.warning(f'Failed to screenshot {url}', exc_info=e)
        return b''
    return png


READABILITY_PATH = which('readability-extractor',
                         '/usr/bin/readability-extractor',  # rpi ubuntu
                         '/usr/local/bin/readability-extractor',  # debian
                         warn=True)


def local_extract_readability(path: str, url: str) -> dict:
    """Extract the readability from an HTML file, typically from single-file."""
    logger.info(f'readability for {url}')
    if not READABILITY_PATH.is_file():
        raise FileNotFoundError(f'Readability extractor not found')

    cmd = (READABILITY_PATH, path, url)
    logger.debug(f'readability cmd: {cmd}')
    output = subprocess.check_output(cmd, timeout=60 * 3)
    output = json.loads(output)
    logger.debug(f'done readability for {url}')
    return output


def local_archive(url: str):
    """Perform an archive of the provided URL using local resources (without the Archive docker container)."""
    # Archives must be performed in the wrolpi home directory because chrome saves the screenshot there, and will
    # raise an error if global $HOME is not a real user directory. :(
    with chdir('/home/wrolpi', with_home=True):
        singlefile = local_singlefile(url)
        with tempfile.NamedTemporaryFile('wb') as fh:
            fh.write(singlefile)
            readability = local_extract_readability(fh.name, url)
        screenshot = local_screenshot(url)
        singlefile = singlefile.decode()
        return singlefile, readability, screenshot


def do_archive(url: str) -> Archive:
    """
    Perform the real archive request to the archiving service.  Store the resulting data into files.  Create an Archive
    record in the DB.  Create Domain/URL if missing.
    """
    logger.info(f'Archiving {url}')

    if DOCKERIZED or PYTEST:
        # Perform the archive in the Archive docker container.  (Typically in the development environment).
        singlefile, readability, screenshot = request_archive(url)
    else:
        # Perform the archive using locally installed executables.
        singlefile, readability, screenshot = local_archive(url)

    # First try to get the title from Readability.
    title = readability.get('title') if readability else None

    if not title and singlefile:
        # Try to get the title ourselves from the HTML.
        title = get_title_from_html(singlefile, url=url)
        if readability:
            # Readability could not find title, lets use ours.
            readability['title'] = title

    archive_files = get_new_archive_files(url, title)

    if readability:
        # Write the readability parts to their own files.  Write what is left after pops to the JSON file.
        with archive_files.readability.open('wt') as fh:
            fh.write(readability.pop('content'))
        with archive_files.readability_txt.open('wt') as fh:
            readability_txt = readability.pop('textContent')
            fh.write(readability_txt)
    else:
        # No readability was returned, so there are no files.
        readability_txt = archive_files.readability_txt = archive_files.readability = None

    # Store the single-file HTML in its own file.
    with archive_files.singlefile.open('wt') as fh:
        fh.write(singlefile)
    if screenshot:
        with archive_files.screenshot.open('wb') as fh:
            fh.write(screenshot)
    else:
        archive_files.screenshot = None

    # Always write a JSON file that contains at least the URL.
    readability = readability or {}
    readability['url'] = url
    with archive_files.readability_json.open('wt') as fh:
        fh.write(json.dumps(readability))

    with get_db_session(commit=True) as session:
        domain = get_or_create_domain(session, url)
        archive = Archive(
            title=title,
            archive_datetime=now(),
            singlefile_path=archive_files.singlefile,
            readability_path=archive_files.readability,
            readability_json_path=archive_files.readability_json,
            readability_txt_path=archive_files.readability_txt,
            screenshot_path=archive_files.screenshot,
            contents=readability_txt,
            url=url,
            domain_id=domain.id,
        )
        session.add(archive)
        session.flush()

    return archive


def get_or_create_domain(session, url) -> Domain:
    """
    Get/create the Domain for this archive.
    """
    domain_ = extract_domain(url)
    domain = session.query(Domain).filter_by(domain=domain_).one_or_none()
    if not domain:
        domain = Domain(domain=domain_, directory=str(get_domain_directory(url)))
        session.add(domain)
        session.flush()
    return domain


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


def delete_archive(archive_id: int):
    """
    Delete an Archive and all of it's files.
    """
    with get_db_session(commit=True) as session:
        archive: Archive = session.query(Archive).filter_by(id=archive_id).one_or_none()
        if not archive:
            raise UnknownURL(f'Unknown Archive with id: {archive_id}')

        # Delete any files associated with this URL.
        archive.delete()


def archive_strptime(dt: str) -> datetime:
    try:
        return local_timezone(datetime.strptime(dt, '%Y-%m-%d-%H-%M-%S'))
    except ValueError:
        return local_timezone(datetime.strptime(dt, '%Y-%m-%d %H:%M:%S'))


def archive_strftime(dt: datetime) -> str:
    return dt.strftime('%Y-%m-%d-%H-%M-%S')


def group_archive_files(files: Iterator[pathlib.Path]) -> groupby:
    """
    Group archive files by their timestamp.
    """
    # groupby requires the files to be sorted.
    files = sorted(files)
    # Group archive files by their datetime at the beginning of the file.
    groups = groupby(files, key=lambda i: i.name[:19])
    for dt, files in groups:
        try:
            dt = archive_strptime(dt)
        except ValueError:
            logger.info(f'Ignoring invalid archives of {dt=}')
            continue

        # Sort the files into their respective slots.
        archive_files = ArchiveFiles()
        file = None
        for file in files:
            name = file.name
            # TODO remove the -readability matching once migrated.
            if name.endswith('.readability.html') or name.endswith('-readability.html'):
                archive_files.readability = file
            elif name.endswith('.html'):
                archive_files.singlefile = file
            elif name.endswith('.png') or name.endswith('.jpg') or name.endswith('.jpeg'):
                archive_files.screenshot = file
            elif name.endswith('.readability.json') or name.endswith('-readability.json'):
                archive_files.readability_json = file
            elif name.endswith('.readability.txt') or name.endswith('-readability.txt'):
                archive_files.readability_txt = file

        if not archive_files.singlefile:
            logger.warning(f'Archive does not have a singlefile html!  Ignoring. {file}')
            continue
        if not archive_files.readability_json:
            logger.warning(f'Archive does not have a json file!  Ignoring. {file}')
            continue

        yield dt, archive_files


OLD_ARCHIVE_MATCHER = re.compile(r'\d{4}-\d\d-\d\d (\d\d:){2}\d\d\.\d{6}.*$')


def migrate_archive_files():
    """
    Rename Archive files from "YYYY-mm-dd HH:MM:SS.ZZZZZ.html" to "YYYY-mm-dd-HH-MM-SS_{TITLE}.html" and all their
    associated files.
    """
    archive_directory = get_archive_directory()

    def _is_archive_file(path: pathlib.Path) -> bool:
        return path.is_file() and path.suffix.lower() in ARCHIVE_SUFFIXES and bool(OLD_ARCHIVE_MATCHER.match(path.name))

    plan = []

    # It is safer to plan the renames before we make them.
    for domain_directory in filter(lambda i: i.is_dir(), archive_directory.iterdir()):
        all_archives_files = filter(_is_archive_file, walk(domain_directory))
        archive_groups = group_archive_files(all_archives_files)
        for dt, archive_files in archive_groups:
            archive_files: ArchiveFiles
            with archive_files.readability_json.open() as fh:
                title = escape_file_name(json.load(fh).get('title') or 'NA')

            title = title[:50]

            dt = archive_strftime(dt)
            prefix = f'{dt}_{title}'
            singlefile_path = domain_directory / f'{prefix}.html'
            readability_path = domain_directory / f'{prefix}.readability.html'
            readability_txt_path = domain_directory / f'{prefix}.readability.txt'
            readability_json_path = domain_directory / f'{prefix}.readability.json'
            screenshot_path = domain_directory / f'{prefix}.png'

            # Every Archive is required to have these files.
            plan.append((archive_files.singlefile, singlefile_path))
            plan.append((archive_files.readability_json, readability_json_path))
            # These files are optional.
            if archive_files.readability:
                plan.append((archive_files.readability, readability_path))
            if archive_files.readability_txt:
                plan.append((archive_files.readability_txt, readability_txt_path))
            if archive_files.screenshot:
                plan.append((archive_files.screenshot, screenshot_path))

    if not plan:
        logger.info('Could not find any Archive files to migrate.  Was it already performed?')
        return plan

    # Check that all new files do not exist.
    for old, new in plan:
        if new.exists():
            raise FileExistsError(f'Cannot migrate archive files! {new} already exists!')

    # Finally, move all the files now that its safe.
    for old, new in plan:
        old.rename(new)

    return plan


ARCHIVE_MATCHER = re.compile(r'\d{4}(-\d\d){5}_.*$')
ARCHIVE_SUFFIXES = {'.txt', '.html', '.json', '.png', '.jpg', '.jpeg'}


def is_archive_file(path: pathlib.Path) -> bool:
    """
    Archive files are expected to start with the following: %Y-%m-%d-%H-%M-%S
    they must have one of the following suffixes: .txt, .html, .json, .png, .jpg, .jpeg
    """
    return path.is_file() and path.suffix.lower() in ARCHIVE_SUFFIXES and bool(ARCHIVE_MATCHER.match(path.name))


def _refresh_archives():
    """
    Search the Archives directory for archive files, update the database if new files are found.  Remove any orphan
    URLs or Domains.
    """
    archive_directory = get_archive_directory()

    # TODO remove this later when everyone has migrated their files.
    migrate_archive_files()

    singlefile_paths = set()
    for domain_directory in filter(lambda i: i.is_dir(), archive_directory.iterdir()):
        logger.debug(f'Refreshing directory: {domain_directory}')
        all_archives_files = filter(is_archive_file, walk(domain_directory))
        archive_groups = group_archive_files(all_archives_files)
        archive_groups = list(archive_groups)
        archive_count = 0
        for chunk in chunks(archive_groups, 20):
            with get_db_session(commit=True) as session:
                for dt, archive_files in chunk:
                    archive_count += 1
                    singlefile_paths.add(str(archive_files.singlefile))
                    upsert_archive(dt, archive_files, session)

        if archive_count:
            logger.info(f'Inserted/updated {archive_count} archives in {domain_directory}')

    singlefile_paths = list(singlefile_paths)
    with get_db_curs(commit=True) as curs:
        curs.execute('DELETE FROM archive WHERE singlefile_path != ALL(%s)', (singlefile_paths,))

    with get_db_curs(commit=True) as curs:
        stmt = '''
            DELETE FROM domains WHERE
                id NOT IN (select distinct domain_id from archive)
            RETURNING domains.id
        '''
        curs.execute(stmt)
        domains = list(map(dict, curs.fetchall()))
        logger.info(f'Deleted {len(domains)} Domains')

    with get_db_session(commit=True) as session:
        # Get all archives that have no text contents, but have txt files.
        archives = session.query(Archive).filter(
            Archive.contents == None,  # noqa
            Archive.readability_txt_path != None,
        ).all()
        for archive in archives:
            with archive.readability_txt_path.path.open('rt') as fh:
                archive.contents = fh.read()


async def refresh_archives():
    _refresh_archives()


def upsert_archive(dt: str, archive_files: ArchiveFiles, session: Session):
    """Get or create an Archive, and it's URL/Domain.  If it already exists, update it with these new files."""
    # Extract the URL from the JSON.  Fail if this is not possible.
    try:
        with archive_files.readability_json.open() as fh:
            json_contents = json.load(fh)
            url = json_contents['url']
            title = json_contents.get('title')
    except Exception as e:
        raise InvalidArchive() from e

    domain = get_or_create_domain(session, url)
    # Get the existing Archive, or create a new one.
    archive = session.query(Archive).filter_by(singlefile_path=archive_files.singlefile).one_or_none()
    if not archive:
        # No archive matches this singlefile_path, create a new one.
        archive = Archive(url=url, domain_id=domain.id)
        session.add(archive)
        session.flush()

    if not archive.title and title:
        archive.title = title
    if not archive.title and archive_files.singlefile:
        # As a last resort, get the title from the HTML.
        archive.title = get_title_from_html(archive_files.singlefile.read_text(), url)

    # Update the archive with the files that we have.
    archive.archive_datetime = dt
    archive.singlefile_path = archive_files.singlefile
    archive.readability_path = archive_files.readability
    archive.readability_txt_path = archive_files.readability_txt
    archive.readability_json_path = archive_files.readability_json
    archive.screenshot_path = archive_files.screenshot


def get_domains():
    with get_db_curs() as curs:
        stmt = '''
            SELECT domains.domain AS domain, COUNT(a.id) AS url_count
            FROM domains
            LEFT JOIN archive a on domains.id = a.domain_id
            GROUP BY domains.domain
            ORDER BY domains.domain
        '''
        curs.execute(stmt)
        domains = list(map(dict, curs.fetchall()))
        return domains


def search(search_str: str, domain: str, limit: int, offset: int) -> Tuple[List[Archive], int]:
    with get_db_curs() as curs:
        columns = 'id, COUNT(*) OVER() AS total'
        params = dict(offset=offset, limit=limit)
        wheres = ''
        order_by = '1 DESC'

        if search_str:
            columns = 'id, ts_rank_cd(textsearch, websearch_to_tsquery(%(search_str)s)), COUNT(*) OVER() AS total'
            params['search_str'] = search_str
            wheres += '\nAND textsearch @@ websearch_to_tsquery(%(search_str)s)'
            # highest rank, then most recent
            order_by = '2 DESC, archive_datetime DESC'

        if domain:
            curs.execute('SELECT id FROM domains WHERE domain=%s', (domain,))
            try:
                domain_id = curs.fetchone()[0]
            except TypeError:
                # No domains match the provided domain.
                return [], 0
            params['domain_id'] = domain_id
            wheres += '\nAND domain_id = %(domain_id)s'

        # TODO handle different Archive search orders.
        stmt = f'''
            SELECT {columns}
            FROM archive
            WHERE
                singlefile_path IS NOT NULL AND singlefile_path != ''
                {wheres}
            ORDER BY {order_by}
            OFFSET %(offset)s
            LIMIT %(limit)s
        '''
        print(stmt, offset, limit)
        curs.execute(stmt, params)
        results = [dict(i) for i in curs.fetchall()]
        total = results[0]['total'] if results else 0
        ranked_ids = [i['id'] for i in results]

    results = get_ranked_models(ranked_ids, Archive)

    return results, total
