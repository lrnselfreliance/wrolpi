import base64
import gzip
import json
import pathlib
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Tuple, List, Union
from urllib.parse import urlparse

import pytz
from sqlalchemy import asc
from sqlalchemy.orm import Session

from modules.archive.models import Domain, Archive
from wrolpi import dates
from wrolpi.common import get_media_directory, logger, extract_domain, escape_file_name, aiohttp_post, \
    format_html_string, split_lines_by_length, get_html_soup
from wrolpi.dates import now, Seconds
from wrolpi.db import get_db_session, get_db_curs, optional_session
from wrolpi.errors import UnknownArchive, InvalidOrderBy, InvalidDatetime
from wrolpi.tags import tag_names_to_file_group_sub_select
from wrolpi.vars import PYTEST

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
        archive.file_group.download_datetime = now()
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
    soup = get_html_soup(html)
    try:
        return soup.title.string
    except Exception:  # noqa
        logger.debug(f'Unable to extract title {url}')


SINGLEFILE_URL_EXTRACTOR = re.compile(r'Page saved with SingleFile \s+url: (http.+?)\n')


def get_url_from_singlefile(html: bytes) -> str:
    """Extract URL from SingleFile contents."""
    html = html.decode()
    if SINGLEFILE_HEADER not in html:
        raise RuntimeError(f'Not a singlefile!')

    url, = SINGLEFILE_URL_EXTRACTOR.findall(html)
    url = url.strip()

    if not url.startswith('http'):
        raise RuntimeError('URL did not start with http')

    # Verify that the URL can be parsed.
    urlparse(url)
    return url


@dataclass
class ArticleMetadata:
    title: str = None
    published_datetime: datetime = None
    modified_datetime: datetime = None
    description: str = None
    author: str = None


def parse_article_html_metadata(html: Union[bytes, str], assume_utc: bool = True) -> ArticleMetadata:
    """
    Read the data from the <meta> tags, extract any data relevant to the article.  This function also reads the
    <script type="application/ld+json"> data.
    """
    metadata = ArticleMetadata()

    soup = get_html_soup(html)

    def get_meta_by_property(prop: str):
        return soup.find('meta', attrs={'property': prop})

    # <meta content="2023-10-18T04:52:23+00:00" property="article:published_time"/>
    if meta_published_time := get_meta_by_property('article:published_time'):
        metadata.published_datetime = dates.strpdate(meta_published_time.attrs['content'])
    # <meta name="article.published" content="2023-04-04T21:52:00.000Z">
    if meta_article_published := soup.find('meta', attrs={'name': 'article.published'}):
        metadata.published_datetime = metadata.published_datetime or dates.strpdate(
            meta_article_published.attrs['content'])
    # <meta itemprop="datePublished" content="2023-04-04T21:52:00.000Z">
    if meta_item_published := soup.find('meta', attrs={'itemprop': 'datePublished'}):
        metadata.published_datetime = metadata.published_datetime or dates.strpdate(
            meta_item_published.attrs['content'])
    # <time itemprop="datePublished" datetime="2023-08-25">
    if time := soup.find('time', attrs={'itemprop': 'datePublished'}):
        metadata.published_datetime = metadata.published_datetime or dates.strpdate(time.attrs['datetime'])
    # <abbr class="published" itemprop="datePublished" title="2022-03-17T03:00:00-07:00">March 17, 2022</abbr>
    if abbr := soup.find('abbr', attrs={'itemprop': 'datePublished'}):
        metadata.published_datetime = metadata.published_datetime or dates.strpdate(abbr.attrs['title'])

    # <meta content="2023-10-19T05:53:24+00:00" property="article:modified_time"/>
    if meta_modified_time := get_meta_by_property('article:modified_time'):
        metadata.modified_datetime = dates.strpdate(meta_modified_time.attrs['content'])
    # <meta name="article.updated" content="2023-04-04T21:52:00.000Z">
    if meta_article_updated := soup.find('meta', attrs={'name': 'article.updated'}):
        metadata.modified_datetime = metadata.modified_datetime or dates.strpdate(meta_article_updated.attrs['content'])

    # <meta content="The Title" property="og:title"/>
    if meta_title := get_meta_by_property('og:title'):
        metadata.title = meta_title.attrs['content']

    # <meta name="author" content="Author Name"/>
    if meta_author := soup.find('meta', attrs={'name': 'author'}):
        metadata.author = meta_author.attrs['content']
    # <meta content="Billy" property="article:author"/>
    if meta_property_author := get_meta_by_property('article:author'):
        metadata.author = metadata.author or meta_property_author.attrs['content']
    # <a href="https://example.com" rel="author">
    if link_author := soup.find('a', attrs={'rel': 'author'}):
        metadata.author = metadata.author or link_author.text.strip()

    # <script class="sf-hidden" type="application/ld+json">
    if (ld_script := soup.find('script', attrs={'type': 'application/ld+json'})) and ld_script.contents:
        try:
            schema = json.loads(ld_script.text)
        except json.decoder.JSONDecodeError:
            # Was not valid JSON.
            schema = None
        if isinstance(schema, dict) and schema.get('@context') in ('https://schema.org', 'http://schema.org'):
            # Found https://schema.org/
            if headline := schema.get('headline'):
                metadata.title = metadata.title or headline
            if datePublished := schema.get('datePublished'):
                try:
                    metadata.published_datetime = metadata.published_datetime or dates.strpdate(datePublished)
                except InvalidDatetime as e:
                    # Invalid date, ignore.
                    logger.error('Invalid datetime', exc_info=e)
                    if PYTEST:
                        raise
            if dateModified := schema.get('dateModified'):
                try:
                    metadata.modified_datetime = metadata.modified_datetime or dates.strpdate(dateModified)
                except InvalidDatetime as e:
                    # Invalid date, ignore.
                    logger.error('Invalid datetime', exc_info=e)
                    if PYTEST:
                        raise
            if description := schema.get('description'):
                metadata.description = description
            if author := schema.get('author'):
                if isinstance(author, list) and len(author) >= 1:
                    # Use the first Author.
                    author = author[0]

                if isinstance(author, dict):
                    author = author.get('name') or author

                if isinstance(author, str):
                    metadata.author = author
                else:
                    logger.warning(f'Unable to parse author schema: {author}')

    # Assume UTC if no timezone.
    if metadata.published_datetime and not metadata.published_datetime.tzinfo and assume_utc:
        logger.debug(f'Assuming UTC for {metadata.published_datetime=}')
        metadata.published_datetime = metadata.published_datetime.replace(tzinfo=pytz.UTC)
    if metadata.modified_datetime and not metadata.modified_datetime.tzinfo and assume_utc:
        logger.debug(f'Assuming UTC for {metadata.modified_datetime=}')
        metadata.modified_datetime = metadata.modified_datetime.replace(tzinfo=pytz.UTC)

    return metadata


@optional_session
def get_archive(session, archive_id: int) -> Archive:
    """Get an Archive."""
    archive = Archive.find_by_id(archive_id, session=session)
    archive.file_group.set_viewed()
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
    'published_datetime': (date := 'fg.published_datetime ASC, fg.download_datetime ASC'),
    '-published_datetime': (_date := 'fg.published_datetime DESC NULLS LAST, fg.download_datetime DESC NULLS LAST'),
    'published_modified_datetime': f'fg.published_modified_datetime ASC NULLS LAST, {date}',
    '-published_modified_datetime': f'fg.published_modified_datetime DESC, {_date}',
    'download_datetime': 'fg.download_datetime ASC',
    '-download_datetime': 'fg.download_datetime DESC',
    'rank': f'2 DESC, {_date}',
    '-rank': f'2 ASC, {date}',
    'size': 'fg.size ASC, LOWER(fg.primary_path) ASC',
    '-size': 'fg.size DESC NULLS LAST, LOWER(fg.primary_path) DESC',
    'viewed': 'fg.viewed ASC',
    '-viewed': 'fg.viewed DESC',
}
ORDER_GROUP_BYS = {
    'published_datetime': 'fg.published_datetime, fg.download_datetime',
    '-published_datetime': 'fg.published_datetime, fg.download_datetime',
    'published_modified_datetime': 'fg.published_modified_datetime, fg.published_datetime, fg.download_datetime',
    '-published_modified_datetime': 'fg.published_modified_datetime, fg.published_datetime, fg.download_datetime',
    'download_datetime': 'fg.download_datetime',
    '-download_datetime': 'fg.download_datetime',
    'rank': 'fg.published_datetime, fg.download_datetime',
    '-rank': 'fg.published_datetime, fg.download_datetime',
    'size': 'fg.size, fg.published_datetime, fg.primary_path',
    '-size': 'fg.size, fg.published_datetime, fg.primary_path',
    'viewed': 'fg.viewed',
    '-viewed': 'fg.viewed',
}
NO_NULL_ORDERS = {
    'viewed': 'fg.viewed IS NOT NULL',
    '-viewed': 'fg.viewed IS NOT NULL',
    'published_modified_datetime': 'fg.published_modified_datetime IS NOT NULL',
    '-published_modified_datetime': 'fg.published_modified_datetime IS NOT NULL',
}


def search_archives(search_str: str, domain: str, limit: int, offset: int, order: str, tag_names: List[str],
                    headline: bool = False) \
        -> Tuple[List[dict], int]:
    # Always filter FileGroups to Archives.
    wheres = []
    group_by = 'fg.published_datetime, fg.download_datetime, a.file_group_id'

    params = dict(search_str=search_str, offset=int(offset), limit=int(limit))
    order_by = ARCHIVE_ORDERS['-published_datetime']

    select_columns = ''
    if search_str:
        # A search_str was provided by the user, modify the query to filter by it.
        select_columns = 'ts_rank(fg.textsearch, websearch_to_tsquery(%(search_str)s)) AS rank,' \
                         ' COUNT(*) OVER() AS total'
        wheres.append('fg.textsearch @@ websearch_to_tsquery(%(search_str)s)')
        params['search_str'] = search_str
        group_by = f'{group_by}, rank'

    if order:
        try:
            order_by = ARCHIVE_ORDERS[order]
            group_by = f'{group_by}, {ORDER_GROUP_BYS[order]}'
        except KeyError:
            raise InvalidOrderBy(f'Invalid order byy {order}')
        if order in NO_NULL_ORDERS:
            wheres.append(NO_NULL_ORDERS[order])

    if tag_names:
        # Filter all FileGroups by those that have been tagged with the provided tag names.
        tags_stmt, params_ = tag_names_to_file_group_sub_select(tag_names)
        params.update(params_)
        wheres.append(f'fg.id = ANY({tags_stmt})')

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
    stmt = f'''
            SELECT
                a.file_group_id AS id, -- always get `file_group.id` for `handle_file_group_search_results`
                COUNT(*) OVER() AS total
                {select_columns}
                {headline}
            FROM archive a
            LEFT JOIN file_group fg ON fg.id = a.file_group_id
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
