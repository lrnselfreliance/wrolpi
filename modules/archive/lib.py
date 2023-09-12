import base64
import gzip
import json
import pathlib
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Tuple, List

from bs4 import BeautifulSoup
from sqlalchemy import asc
from sqlalchemy.orm import Session

from modules.archive.models import Domain, Archive
from wrolpi.common import get_media_directory, logger, extract_domain, escape_file_name, aiohttp_post, \
    format_html_string, split_lines_by_length
from wrolpi.dates import now, Seconds
from wrolpi.db import get_db_session, get_db_curs, optional_session
from wrolpi.errors import UnknownArchive, InvalidOrderBy
from wrolpi.tags import tag_names_to_file_group_sub_select

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
    return archive_directory


def get_domain_directory(url: str) -> pathlib.Path:
    """Get the archive directory for a particular domain."""
    domain = extract_domain(url)
    directory = get_archive_directory() / domain
    if directory.is_dir():
        return directory
    elif directory.exists():
        raise FileNotFoundError(f'Domain directory {directory} is already a file')

    directory.mkdir(parents=True, exist_ok=True)
    return directory


MAXIMUM_ARCHIVE_FILE_CHARACTER_LENGTH = 200


def get_new_archive_files(url: str, title: Optional[str]) -> ArchiveFiles:
    """Create a list of archive files using a shared name schema.  Raise an error if any of them exist."""
    directory = get_domain_directory(url)
    # Datetime is valid in Linux and Windows.
    dt = archive_strftime(now())

    title = escape_file_name(title or 'NA')
    title = title[:MAXIMUM_ARCHIVE_FILE_CHARACTER_LENGTH]
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

        readability = contents.get('readability')
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


async def model_archive_result(url: str, singlefile: str, readability: dict, screenshot: bytes) -> Archive:
    """
    Convert results from ArchiveDownloader into real files.  Create Archive record.
    """
    readability = readability.copy() if readability else readability
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
            content = format_html_string(readability.pop('content'))
            fh.write(content)
        with archive_files.readability_txt.open('wt') as fh:
            readability_txt = readability.pop('textContent')
            readability_txt = split_lines_by_length(readability_txt)
            fh.write(readability_txt)
    else:
        # No readability was returned, so there are no files.
        archive_files.readability_txt = archive_files.readability = None

    # Store the single-file HTML in its own file.
    singlefile = format_html_string(singlefile)
    archive_files.singlefile.write_text(singlefile)

    if screenshot:
        archive_files.screenshot.write_bytes(screenshot)
    else:
        archive_files.screenshot = None

    # Always write a JSON file that contains at least the URL.
    readability = readability or {}
    readability['url'] = url
    with archive_files.readability_json.open('wt') as fh:
        fh.write(json.dumps(readability, indent=2))

    # Create any File models that we can, index them all.
    paths = (
        archive_files.singlefile, archive_files.readability, archive_files.readability_json,
        archive_files.readability_txt,
        archive_files.screenshot)
    paths = list(filter(None, paths))

    with get_db_session(commit=True) as session:
        archive = Archive.from_paths(session, *paths)
        archive.archive_datetime = now()
        archive.url = url
        archive.domain = get_or_create_domain(session, url)
        session.flush()

    return archive


def get_or_create_domain(session: Session, url) -> Domain:
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
    archive = Archive.find_by_id(archive_id, session=session)
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


def archive_strftime(dt: datetime) -> str:
    return dt.strftime('%Y-%m-%d-%H-%M-%S')


ARCHIVE_MATCHER = re.compile(r'\d{4}(-\d\d){5}_.*$')
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
        # Lastly, try to read the header of this HTML file.  Read a large part of the head because URLs can be long.
        header = fh.read(1000)
        if SINGLEFILE_HEADER in header:
            return True
    return False


def get_domains():
    with get_db_curs() as curs:
        stmt = '''
            SELECT domains.domain AS domain, COUNT(a.id) AS url_count, SUM(fg.size)::BIGINT AS size
            FROM domains
                LEFT JOIN archive a on domains.id = a.domain_id
                LEFT JOIN file_group fg on fg.id = a.file_group_id
            GROUP BY domains.domain
            ORDER BY domains.domain
        '''
        curs.execute(stmt)
        domains = [dict(i) for i in curs.fetchall()]
        return domains


ARCHIVE_ORDERS = {
    'date': 'a.archive_datetime ASC',
    '-date': 'a.archive_datetime DESC NULLS LAST',
    'rank': '2 DESC, a.archive_datetime DESC',
    '-rank': '2 ASC, a.archive_datetime ASC',
    'size': 'fg.size ASC, LOWER(fg.primary_path) ASC',
    '-size': 'fg.size DESC NULLS LAST, LOWER(fg.primary_path) DESC',
}
ORDER_GROUP_BYS = {
    'date': 'a.archive_datetime',
    '-date': 'a.archive_datetime',
    'rank': 'a.archive_datetime',
    '-rank': 'a.archive_datetime',
    'size': 'fg.size, fg.primary_path',
    '-size': 'fg.size, fg.primary_path',
}
FILE_ORDERS = ['size', '-size']


def search_archives(search_str: str, domain: str, limit: int, offset: int, order: str, tag_names: List[str],
                    headline: bool = False) \
        -> Tuple[List[dict], int]:
    # Always filter FileGroups to Archives.
    wheres = []
    joins = []
    group_by = 'a.file_group_id'

    params = dict(search_str=search_str, offset=int(offset), limit=int(limit))
    order_by = 'id DESC'

    select_columns = ''
    if search_str:
        # A search_str was provided by the user, modify the query to filter by it.
        select_columns = 'ts_rank(fg.textsearch, websearch_to_tsquery(%(search_str)s)) AS rank,' \
                         ' COUNT(*) OVER() AS total'
        wheres.append('fg.textsearch @@ websearch_to_tsquery(%(search_str)s)')
        params['search_str'] = search_str
        joins = ['LEFT JOIN file_group fg ON fg.id = a.file_group_id']
        group_by = f'{group_by}, rank'

    if order:
        try:
            order_by = ARCHIVE_ORDERS[order]
            group_by = f'{group_by}, {ORDER_GROUP_BYS[order]}'
            if order in FILE_ORDERS:
                joins = ['LEFT JOIN file_group fg ON fg.id = a.file_group_id']
        except KeyError:
            raise InvalidOrderBy(f'Invalid order by: {order}')

    if tag_names:
        # Filter all FileGroups by those that have been tagged with the provided tag names.
        tags_stmt, params_ = tag_names_to_file_group_sub_select(tag_names)
        params.update(params_)
        wheres.append(f'fg.id = ANY({tags_stmt})')
        joins = ['LEFT JOIN file_group fg ON fg.id = a.file_group_id']

    if search_str and headline:
        headline = ''',
                ts_headline(fg.title, websearch_to_tsquery(%(search_str)s)) AS "title_headline",
                ts_headline(fg.b_text, websearch_to_tsquery(%(search_str)s)) AS "b_headline",
                ts_headline(fg.c_text, websearch_to_tsquery(%(search_str)s)) AS "c_headline",
                ts_headline(fg.d_text, websearch_to_tsquery(%(search_str)s)) AS "d_headline"'''
        group_by = f'{group_by}, title_headline, b_headline, c_headline, d_headline'
    else:
        headline = ''

    if domain:
        params['domain'] = domain
        wheres.append('a.domain_id = (select id from domains where domains.domain = %(domain)s)')

    select_columns = f", {select_columns}" if select_columns else ""
    wheres = '\n AND '.join(wheres)
    where = f'WHERE\n{wheres}' if wheres else ''
    join = '\n'.join(joins)
    stmt = f'''
            SELECT
                a.file_group_id AS id, -- always get `file_group.id` for `handle_file_group_search_results`
                COUNT(*) OVER() AS total
                {select_columns}
                {headline}
            FROM archive a
            {join}
            {where}
            GROUP BY {group_by}
            ORDER BY {order_by}
            OFFSET %(offset)s LIMIT %(limit)s
        '''.strip()
    logger.debug(stmt, params)

    from wrolpi.files.lib import handle_file_group_search_results
    results, total = handle_file_group_search_results(stmt, params)
    return results, total


@optional_session
def search_domains_by_name(name: str, limit: int = 5, session: Session = None) -> List[Domain]:
    domains = session.query(Domain) \
        .filter(Domain.domain.ilike(f'%{name}%')) \
        .order_by(asc(Domain.domain)) \
        .limit(limit) \
        .all()
    return domains
