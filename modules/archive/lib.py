import base64
import gzip
import json
import pathlib
import re
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from itertools import groupby
from typing import Iterator, Optional, Tuple, List

from bs4 import BeautifulSoup
from selenium import webdriver

from modules.archive.models import Domain, Archive
from wrolpi.cmd import READABILITY_BIN, SINGLE_FILE_BIN, CHROMIUM
from wrolpi.common import get_media_directory, logger, extract_domain, chdir, escape_file_name, walk, \
    aiohttp_post, match_paths_to_suffixes, iterify
from wrolpi.dates import now, Seconds
from wrolpi.db import get_db_session, get_db_curs, optional_session
from wrolpi.errors import UnknownArchive, InvalidOrderBy
from wrolpi.files.lib import handle_search_results
from wrolpi.files.models import File
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


async def request_archive(url: str) -> Tuple[str, Optional[str], Optional[str]]:
    """Send a request to the archive service to archive the URL."""
    logger.info(f'Sending archive request to archive service: {url}')

    data = {'url': url}
    try:
        contents, status = await aiohttp_post(f'{ARCHIVE_SERVICE}/json', json_=data, timeout=ARCHIVE_TIMEOUT)
        if contents and (error := contents.get('error')):
            # Report the error from the archive service.
            raise Exception(f'Received error from archive service: {error}')

        readability = contents['readability']
        # Compressed base64
        singlefile = contents['singlefile']
        screenshot = contents['screenshot']

        logger.debug(f'archive request status code {status}')
    except Exception as e:
        logger.error('Error when requesting archive', exc_info=e)
        raise

    if not (screenshot or singlefile or readability):
        raise Exception('singlefile response was empty!')

    if not readability:
        logger.info(f'Failed to get readability for {url=}')

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


def local_singlefile(url: str):
    """Run the single-file executable to create an HTML file archive."""
    if not SINGLE_FILE_BIN or not SINGLE_FILE_BIN.is_file():
        raise FileNotFoundError(f'single-file not found.  Is it installed?')

    cmd = (str(SINGLE_FILE_BIN),
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


def local_extract_readability(path: str, url: str) -> dict:
    """Extract the readability from an HTML file, typically from single-file."""
    logger.info(f'readability for {url}')
    if not READABILITY_BIN.is_file():
        raise FileNotFoundError(f'Readability extractor not found')

    cmd = (READABILITY_BIN, path, url)
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


async def do_archive(url: str) -> Archive:
    """
    Perform the real archive request to the archiving service.  Store the resulting data into files.  Create an Archive
    record in the DB.  Create Domain if missing.
    """
    logger.info(f'Archiving {url}')

    if DOCKERIZED or PYTEST:
        # Perform the archive in the Archive docker container.  (Typically in the development environment).
        singlefile, readability, screenshot = await request_archive(url)
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
        archive_files.readability_txt = archive_files.readability = None

    # Store the single-file HTML in its own file.
    archive_files.singlefile.write_text(singlefile)

    if screenshot:
        archive_files.screenshot.write_bytes(screenshot)
    else:
        archive_files.screenshot = None

    # Always write a JSON file that contains at least the URL.
    readability = readability or {}
    readability['url'] = url
    with archive_files.readability_json.open('wt') as fh:
        fh.write(json.dumps(readability))

    # Create any File models that we can, index them all.
    singlefile_file = File(path=archive_files.singlefile, model='archive')
    singlefile_file.do_index()
    readability_file = None
    if archive_files.readability:
        readability_file = File(path=archive_files.readability, associated=True)
        readability_file.do_index()
    readability_json_file = None
    if archive_files.readability_json:
        readability_json_file = File(path=archive_files.readability_json, associated=True)
        readability_json_file.do_index()
    readability_txt_file = None
    if archive_files.readability_txt:
        readability_txt_file = File(path=archive_files.readability_txt, associated=True)
        readability_txt_file.do_index()
    screenshot_file = None
    if archive_files.screenshot:
        screenshot_file = File(path=archive_files.screenshot, associated=True)
        screenshot_file.do_index()

    with get_db_session(commit=True) as session:
        domain = get_or_create_domain(session, url)
        archive = Archive(
            title=title,
            archive_datetime=now(),
            singlefile_file=singlefile_file,
            readability_file=readability_file,
            readability_json_file=readability_json_file,
            readability_txt_file=readability_txt_file,
            screenshot_file=screenshot_file,
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


@optional_session
def get_archive(session, archive_id: int) -> Archive:
    """Get an Archive."""
    archive = session.query(Archive).filter_by(id=archive_id).one_or_none()
    if not archive:
        raise UnknownArchive(f'Could not find archive with id: {archive_id}')
    return archive


def delete_archives(*archive_ids: List[int]):
    """Delete an Archive and all of it's files."""
    with get_db_session(commit=True) as session:
        archives: List[Archive] = list(session.query(Archive).filter(Archive.id.in_(archive_ids)))
        if not archives:
            raise UnknownArchive(f'Unknown Archives with IDs: {", ".join(map(str, archive_ids))}')

        # Delete any files associated with this URL.
        for archive in archives:
            archive.delete()


def archive_strptime(dt: str) -> datetime:
    try:
        return datetime.strptime(dt, '%Y-%m-%d-%H-%M-%S')
    except ValueError:
        return datetime.strptime(dt, '%Y-%m-%d %H:%M:%S')


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


SINGLEFILE_HEADER = '''<!--
 Page saved with SingleFile'''


def is_singlefile_file(path: pathlib.Path) -> bool:
    """
    Archive singlefile files are expected to start with the following: %Y-%m-%d-%H-%M-%S
    they must end with .html, but never with .readability.html.
    """
    if not path.is_file() or \
            path.suffix.lower() != '.html' or \
            path.name.lower().endswith('.readability.html') or \
            path.stat().st_size == 0:
        return False
    if ARCHIVE_MATCHER.match(path.name):
        # A file name matching exactly the Archive format from WROLPi should always be an Archive.
        return True
    with path.open('rt') as fh:
        # Lastly, try to read the header of this HTML file.
        header = fh.read(1000)
        if SINGLEFILE_HEADER in header:
            return True
    return False


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


ARCHIVE_ORDERS = {
    'date': 'a.archive_datetime ASC, LOWER(a.singlefile_path) ASC',
    '-date': 'a.archive_datetime DESC NULLS LAST, LOWER(a.singlefile_path) DESC',
    'rank': '2 DESC, a.archive_datetime DESC',
    '-rank': '2 ASC, a.archive_datetime ASC',
}


def archive_search(search_str: str, domain: str, limit: int, offset: int, order_by: str) -> Tuple[List[Archive], int]:
    wheres = []

    params = dict(search_str=search_str, offset=int(offset), limit=int(limit))
    order = '1 DESC'

    if search_str:
        # A search_str was provided by the user, modify the query to filter by it.
        select_columns = 'f.path, ts_rank(f.textsearch, websearch_to_tsquery(%(search_str)s)), COUNT(*) OVER() AS total'
        wheres.append('f.textsearch @@ websearch_to_tsquery(%(search_str)s)')
        params['search_str'] = search_str
        join = 'LEFT JOIN file f on f.path = a.singlefile_path'
    else:
        # No search_str provided.  Get path and total only.  Don't join the "file" to speed up query.
        select_columns = 'a.singlefile_path AS path, COUNT(*) OVER() AS total'
        join = ''

    if order_by:
        try:
            order = ARCHIVE_ORDERS[order_by]
        except KeyError:
            raise InvalidOrderBy(f'Invalid order by: {order_by}')

    if domain:
        params['domain'] = domain
        wheres.append('domain_id = (select id from domains where domains.domain = %(domain)s)')

    wheres = '\n AND '.join(wheres)
    where = f'WHERE\n{wheres}' if wheres else ''
    stmt = f'''
            SELECT
                {select_columns}
            FROM archive a
            {join}
            {where}
            ORDER BY {order}
            OFFSET %(offset)s LIMIT %(limit)s
        '''.strip()
    logger.debug(stmt, params)

    results, total = handle_search_results(stmt, params)
    return results, total


match_archive_paths = partial(match_paths_to_suffixes, suffix_groups=(
    ('.readability.html',),
    ('.html',),
    ('.readability.json',),
    ('.readability.txt',),
    ('.jpg', '.jpeg', '.webp', '.png'),
))


@iterify(tuple)
def match_archive_files(files: List[File]) -> Tuple[File, File, File, File, File]:
    archive_paths = match_archive_paths([i.path for i in files])
    for path in archive_paths:
        yield next((i for i in files if i.path == path), None)
