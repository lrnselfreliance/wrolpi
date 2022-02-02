import base64
import gzip
import json
import pathlib
import re
import subprocess
import tempfile
from datetime import datetime
from itertools import groupby
from typing import Iterator, Optional

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from sqlalchemy.orm import Session

from modules.archive.models import Domain, Archive
from wrolpi.common import get_media_directory, logger, chunks, extract_domain, chdir, escape_file_name, walk
from wrolpi.dates import now, Seconds, local_timezone
from wrolpi.db import get_db_session, get_db_curs, get_ranked_models
from wrolpi.errors import InvalidDomain, UnknownURL, InvalidArchive
from wrolpi.vars import DOCKERIZED, PYTEST

logger = logger.getChild(__name__)

ARCHIVE_SERVICE = 'http://archive:8080'


def get_archive_directory() -> pathlib.Path:
    archive_directory = get_media_directory() / 'archive'
    if not archive_directory.is_dir():
        archive_directory.mkdir()
    return archive_directory


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


def get_new_archive_files(url: str, title: Optional[str]):
    """
    Create a list of archive files using a shared name schema.  Raise an error if any of them exist.
    """
    directory = get_domain_directory(url)
    dt = now().strftime('%Y-%m-%d-%H-%M-%S')

    title = escape_file_name(title or 'NA')
    prefix = f'{dt}_{title}'
    singlefile_path = directory / f'{prefix}.html'
    readability_path = directory / f'{prefix}-readability.html'
    readability_txt_path = directory / f'{prefix}-readability.txt'
    readability_json_path = directory / f'{prefix}-readability.json'
    screenshot_path = directory / f'{prefix}.png'

    ret = (singlefile_path, readability_path, readability_txt_path, readability_json_path, screenshot_path)

    for path in ret:
        if path.exists():
            raise FileExistsError(f'New archive file already exists: {path}')

    return ret


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


def local_singlefile(url: str):
    """
    Run the single-file executable to create an HTML file archive.
    """
    single_file_path = pathlib.Path('/usr/bin/single-file')
    if not single_file_path.is_file():
        raise FileNotFoundError(f'single-file not found at {single_file_path}')

    cmd = (str(single_file_path),
           url,
           '--browser-executable-path', '/usr/bin/chromium-browser',
           '--browser-args', '["--no-sandbox"]',
           '--dump-content')
    logger.debug(f'archive cmd: {cmd}')
    output = subprocess.check_output(cmd, timeout=60 * 3)
    logger.debug(f'done archiving for {url}')
    return output


def local_screenshot(url: str) -> bytes:
    """
    Take a screenshot of the URL using selenium.
    """
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
    """
    Extract the readability from an HTML file, typically from single-file.
    """
    logger.info(f'readability for {url}')
    readability_path = pathlib.Path('/usr/bin/readability-extractor')
    if not readability_path.is_file():
        raise FileNotFoundError(f'Readability extractor not found at {readability_path}')

    cmd = (readability_path, path, url)
    logger.debug(f'readability cmd: {cmd}')
    output = subprocess.check_output(cmd, timeout=60 * 3)
    output = json.loads(output)
    logger.debug(f'done readability for {url}')
    return output


def local_archive(url: str):
    """
    Perform an archive of the provided URL using local resources (without the Archive docker container).
    """
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

    singlefile_path, readability_path, readability_txt_path, readability_json_path, screenshot_path = \
        get_new_archive_files(url, title)

    if readability:
        # Write the readability parts to their own files.  Write what is left after pops to the JSON file.
        with readability_path.open('wt') as fh:
            fh.write(readability.pop('content'))
        with readability_txt_path.open('wt') as fh:
            readability_txt = readability.pop('textContent')
            fh.write(readability_txt)
    else:
        # No readability was returned, so there are no files.
        readability_txt = readability_path = readability_txt_path = None

    # Store the single-file HTML in its own file.
    with singlefile_path.open('wt') as fh:
        fh.write(singlefile)
    if screenshot:
        with screenshot_path.open('wb') as fh:
            fh.write(screenshot)
    else:
        screenshot_path = None

    # Always write a JSON file that contains at least the URL.
    readability = readability or {}
    readability['url'] = url
    with readability_json_path.open('wt') as fh:
        fh.write(json.dumps(readability))

    with get_db_session(commit=True) as session:
        domain = get_or_create_domain(session, url)
        archive = Archive(
            title=title,
            archive_datetime=now(),
            singlefile_path=singlefile_path,
            readability_path=readability_path,
            readability_json_path=readability_json_path,
            readability_txt_path=readability_txt_path,
            screenshot_path=screenshot_path,
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
NEW_ARCHIVE_MATCHER = re.compile(r'\d{4}-(\d{2}-){4}\d\d_.*$')
ARCHIVE_SUFFIXES = {'.txt', '.html', '.json', '.png', '.jpg', '.jpeg'}


def is_archive_file(path: pathlib.Path) -> bool:
    """
    Archive files are expected to start with the following: %Y-%m-%d-%H-%M-%S
    they must have one of the following suffixes: .txt, .html, .json, .png, .jpg, .jpeg
    """
    if not path.is_file():
        return False
    if path.suffix.lower() not in ARCHIVE_SUFFIXES:
        return False
    if bool(ARCHIVE_MATCHER.match(path.name)) or bool(NEW_ARCHIVE_MATCHER.match(path.name)):
        return True
    return False


def _refresh_archives():
    """
    Search the Archives directory for archive files, update the database if new files are found.  Remove any orphan
    URLs or Domains.
    """
    archive_directory = get_archive_directory()

    singlefile_paths = set()
    for domain_directory in filter(lambda i: i.is_dir(), archive_directory.iterdir()):
        logger.debug(f'Refreshing directory: {domain_directory}')
        archives_files = filter(is_archive_file, walk(domain_directory))
        archive_groups = group_archive_files(archives_files)
        archive_count = 0
        for chunk in chunks(archive_groups, 20):
            archive_count += 1
            with get_db_session(commit=True) as session:
                for dt, files in chunk:
                    singlefile_paths.add(str(files[0]))
                    upsert_archive(dt, files, session)

        if archive_count:
            logger.info(f'Inserted/updated {archive_count} archives')

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


def upsert_archive(dt: str, files, session: Session):
    """
    Get or create an Archive and it's URL/Domain.  If it already exists, update it with these new files.
    """
    singlefile_path, readability_path, readability_txt_path, readability_json_path, screenshot_path = files
    # Extract the URL from the JSON.  Fail if this is not possible.
    print(singlefile_path, readability_json_path)
    try:
        with readability_json_path.open() as fh:
            json_contents = json.load(fh)
            url = json_contents['url']
    except Exception as e:
        raise InvalidArchive() from e

    domain = get_or_create_domain(session, url)
    # Get the existing Archive, or create a new one.
    archive = session.query(Archive).filter_by(singlefile_path=singlefile_path).one_or_none()
    if not archive:
        # No archive matches this singlefile_path, create a new one.
        archive = Archive(
            url=url,
            domain_id=domain.id,
        )
        session.add(archive)
        session.flush()

    # Update the archive with the files that we have.
    archive.archive_datetime = dt
    archive.singlefile_path = singlefile_path
    archive.readability_path = readability_path
    archive.readability_txt_path = readability_txt_path
    archive.readability_json_path = readability_json_path
    archive.screenshot_path = screenshot_path


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


def search(search_str: str, domain: str, limit: int, offset: int):
    with get_db_curs() as curs:
        columns = 'id, COUNT(*) OVER() AS total'
        params = dict(offset=offset, limit=limit)
        wheres = ''

        if search_str:
            columns = 'id, ts_rank_cd(textsearch, websearch_to_tsquery(%(search_str)s)), COUNT(*) OVER() AS total'
            params['search_str'] = search_str
            wheres += '\nAND textsearch @@ websearch_to_tsquery(%(search_str)s)'

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
            ORDER BY 2 DESC, archive_datetime DESC  -- highest rank, then most recent
            OFFSET %(offset)s
            LIMIT %(limit)s
        '''
        curs.execute(stmt, params)
        results = [dict(i) for i in curs.fetchall()]
        total = results[0]['total'] if results else 0
        ranked_ids = [i['id'] for i in results]

    results = get_ranked_models(ranked_ids, Archive)

    return results, total
