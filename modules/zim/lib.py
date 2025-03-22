import asyncio
import functools
import pathlib
import re
from datetime import datetime
from typing import List, Tuple, Dict

import cachetools.func
from libzim import Entry
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import NoResultFound  # noqa

from modules.zim import kiwix
from modules.zim.errors import UnknownZim, UnknownZimSubscription
from modules.zim.kiwix import KIWIX_CATALOG
from modules.zim.models import Zim, Zims, TagZimEntry, ZimSubscription
from wrolpi import flags
from wrolpi.cmd import run_command
from wrolpi.common import register_modeler, logger, extract_html_text, extract_headlines, get_media_directory, walk, \
    register_refresh_cleanup, background_task, get_wrolpi_config, unique_by_predicate
from wrolpi.db import get_db_session, optional_session, get_db_curs
from wrolpi.downloader import DownloadFrequency
from wrolpi.files.lib import refresh_files, split_file_name_words
from wrolpi.files.models import FileGroup
from wrolpi.vars import PYTEST, DOCKERIZED

logger = logger.getChild(__name__)

__all__ = [
    'flag_outdated_zim_files',
    'get_all_entries_tags',
    'get_entries_tags',
    'get_entry',
    'get_kiwix_catalog',
    'get_unique_paths',
    'get_zim',
    'get_zims',
    'model_zim',
    'zim_download_url_to_name',
    'zim_modeler',
]


def model_zim(file_group: FileGroup, session: Session) -> Zim:
    """Create a Zim record for the provided FileGroup."""
    zim = Zim(file_group=file_group, path=file_group.primary_path)
    session.add(zim)
    file_group.title = file_group.primary_path.name
    file_group.a_text = split_file_name_words(file_group.primary_path.name)
    file_group.indexed = True
    file_group.model = 'zim'
    return zim


@register_modeler
async def zim_modeler():
    while True:
        with get_db_session(commit=True) as session:
            file_groups = session.query(FileGroup, Zim) \
                .filter(FileGroup.indexed != True,  # noqa
                        FileGroup.primary_path.ilike('%.zim'),
                        ) \
                .outerjoin(Zim, Zim.file_group_id == FileGroup.id) \
                .limit(10)
            file_groups: List[Tuple[FileGroup, Zim]] = list(file_groups)

            processed = 0
            for file_group, zim in file_groups:
                processed += 1

                zim_id = None
                try:
                    if not zim:
                        zim = model_zim(file_group, session)
                        zim.flush()
                    else:
                        zim_id = zim.id
                        file_group.title = file_group.primary_path.name
                        file_group.a_text = split_file_name_words(file_group.primary_path.name)
                        file_group.indexed = True
                        file_group.model = 'zim'
                except Exception as e:
                    if PYTEST:
                        raise
                    logger.error(f'Unable to model Zim {zim_id=} {file_group.primary_path=}', exc_info=e)

            logger.debug(f'Modeled {processed} zim files')

            if processed < 10:
                # Did not reach limit, do not query again.
                break

        # Sleep to catch cancel.
        await asyncio.sleep(0)


def get_all_entries_tags():
    """Returns a dict of dicts which contain the names of all Tags of each Entry's path.

    Example:
        {
            1: {
                    'path1': ['tag1', 'tag2'],
            },
            2: {
                    'path2': ['tag1'],
            },
        """
    stmt = '''
        SELECT tz.zim_id, tz.zim_entry, array_agg(t.name)::TEXT[]
        FROM
            tag t
            LEFT JOIN tag_zim tz on t.id = tz.tag_id
        GROUP BY 1, 2
    '''
    with get_db_curs() as curs:
        curs.execute(stmt)
        entries = dict()
        for zim_id, zim_entry, tag_names in curs.fetchall():
            if not zim_id:
                continue
            try:
                entries[zim_id][zim_entry] = tag_names
            except KeyError:
                entries[zim_id] = {zim_entry: tag_names}
    return entries


def get_entries_tags(paths: List[str], zim_id: int):
    all_entries_tags = get_all_entries_tags()
    entries = dict()
    for path in paths:
        zim_tag_entries = all_entries_tags.get(zim_id, dict())
        entries[path] = zim_tag_entries.get(path, list())

    return entries


def get_unique_paths(*paths: str) -> List[str]:
    """Return a new list which contains unique Zim paths."""
    unique_paths = unique_by_predicate(
        paths,
        lambda i: i.replace('-', '').replace('_', '').replace('/', '').lower()
    )
    return list(unique_paths)


@optional_session
def headline_zim(search_str: str, zim_id: int, tag_names: List[str] = None, offset: int = 0, limit: int = 10,
                 session: Session = None) -> Dict:
    zim_id = int(zim_id)
    zim = get_zim(zim_id, session=session)

    if tag_names:
        # TODO what is the count goes over the limit?
        entries = zim.entries_with_tags(tag_names, offset=offset, limit=1_000, session=session)
        estimate = 0
    elif search_str:
        # Get suggested results (this searches titles).
        results = zim.suggest(search_str, offset, limit)
        search_results = zim.search(search_str, offset, limit)
        # Remove duplicate entries (disambiguation or redirect).
        results = get_unique_paths(*results, *search_results)
        results = results[:limit]
        entries = [zim.find_entry(i) for i in results]
        estimate = zim.estimate(search_str)
    else:
        raise RuntimeError('Must provide search_str or tag_names.')

    articles = [bytes(i.get_item().content).decode('UTF-8') for i in entries]
    articles = [extract_html_text(i) for i in articles]

    entries_tag_names = get_entries_tags([i.path for i in entries], zim_id)

    # Always get headlines even if there is no search_str.  This is because Postgres will return the start of each
    # article.
    headlines = extract_headlines(articles, search_str)

    search = list()
    if search_str:
        # `search_str` allows us to headline the title.
        titles = [i.title for i in entries]
        headline_titles = extract_headlines(titles, search_str)

        for entry in entries:
            title_headline, title_rank = headline_titles.pop(0)
            headline, rank = headlines.pop(0)
            if rank > 0 or title_rank > 0:
                # The result for each Entry.
                path = entry.path
                entry_tag_names = entries_tag_names[path] if path in entries_tag_names else list()
                search.append(dict(
                    headline=headline,
                    path=path,
                    rank=max(rank, title_rank),
                    tag_names=entry_tag_names,
                    title=title_headline,
                ))
                if tag_names:
                    estimate += 1
    else:
        # No `search_str`, we return all entries.
        for entry in entries:
            headline, _ = headlines.pop(0)
            path = entry.path
            entry_tag_names = entries_tag_names[path] if path in entries_tag_names else list()
            search.append(dict(
                headline=headline,
                path=path,
                rank=0,
                tag_names=entry_tag_names,
                title=entry.title,
            ))
        estimate = len(entries)

    results = dict(
        path=zim.path,
        metadata=zim.zim_metadata,
        search=search,
        estimate=estimate,
    )
    return results


@cachetools.func.mru_cache(maxsize=1_000)
def get_estimates(search_str: str) -> List[int]:
    zims = Zims.get_all()
    estimates = [i.estimate(search_str) for i in zims]
    return estimates


@optional_session
def get_zim(zim_id: int, session: Session = None) -> Zim:
    """Return the Zim record of the provided path.

    @raise UnknownZim: When no record exists with the id.
    @warning: Results are cached."""
    try:
        zim: Zim = session.query(Zim) \
            .join(FileGroup, FileGroup.id == Zim.file_group_id) \
            .filter(Zim.id == zim_id) \
            .one()
        return zim
    except Exception as e:
        raise UnknownZim() from e


@functools.lru_cache(maxsize=1_000)
def get_entry(path: str, zim_id: int) -> Entry:
    with get_db_session() as session:
        zim = get_zim(zim_id, session=session)
        entry = zim.find_entry(path)
    return entry


@optional_session
def get_zims(ids: List[int] = None, session: Session = None) -> List[Zim]:
    if ids:
        zims = session.query(Zim).filter(Zim.id.in_(ids)).all()
    else:
        zims = Zims.get_all(session=session)

    return zims


@optional_session(commit=True)
def delete_zims(ids: List[int], session: Session = None):
    zims = get_zims(ids, session=session)
    for zim in zims:
        zim.delete()


@optional_session
async def add_tag(tag_name: str, zim_id: int, zim_entry: str, session: Session = None) -> TagZimEntry:
    zim = session.query(Zim).filter_by(id=zim_id).one()
    tag_zim_entry = zim.tag_entry(tag_name, zim_entry)
    session.commit()
    return tag_zim_entry


@optional_session
async def untag(tag_name: str, zim_id: int, zim_entry: str, session: Session = None):
    zim: Zim = session.query(Zim).filter_by(id=zim_id).one()
    zim.untag_entry(tag_name, zim_entry)
    session.commit()


def get_kiwix_catalog():
    return KIWIX_CATALOG.copy()


@optional_session
def get_kiwix_subscriptions(session: Session = None) -> Dict[str, ZimSubscription]:
    subscriptions = session.query(ZimSubscription)
    subscriptions_by_name = {i.name: i for i in subscriptions}
    return subscriptions_by_name


@optional_session(commit=True)
async def subscribe(name: str, language: str, session: Session = None,
                    frequency: int = DownloadFrequency.days180) -> ZimSubscription:
    subscription = ZimSubscription.get_or_create(name, session=session)
    subscription.language = language

    if name == 'Wikipedia (with images)':
        url = f'https://download.kiwix.org/zim/wikipedia/wikipedia_{language}_all_maxi_'
    elif name == 'Wikipedia (mini)':
        url = f'https://download.kiwix.org/zim/wikipedia/wikipedia_{language}_all_mini_'
    elif name == 'Wikipedia (no images)':
        url = f'https://download.kiwix.org/zim/wikipedia/wikipedia_{language}_all_nopic_'
    elif name == 'Wikiversity (with images)':
        url = f'https://download.kiwix.org/zim/wikiversity/wikiversity_{language}_all_maxi_'
    elif name == 'Wikiversity (no images)':
        url = f'https://download.kiwix.org/zim/wikiversity/wikiversity_{language}_all_nopic_'
    elif name == 'Wikitionary (no images)':
        url = f'https://download.kiwix.org/zim/wiktionary/wiktionary_{language}_all_nopic_'
    elif name == 'Wikitionary (with images)':
        url = f'https://download.kiwix.org/zim/wikiversity/wikiversity_{language}_all_maxi_'
    elif name == 'Wikibooks (no images)':
        url = f'https://download.kiwix.org/zim/wikibooks/wikibooks_{language}_all_nopic_'
    elif name == 'Wikibooks (with images)':
        url = f'https://download.kiwix.org/zim/wikibooks/wikibooks_{language}_all_maxi_'
    elif name == 'Wikisource':
        url = f'https://download.kiwix.org/zim/wikisource/wikisource_{language}_all_maxi_'
    elif name == 'Raspberry Pi (Stack Exchange)':
        url = f'https://download.kiwix.org/zim/stack_exchange/raspberrypi.stackexchange.com_{language}_all_'
    elif name == 'Vikidia':
        url = f'https://download.kiwix.org/zim/vikidia/vikidia_{language}_all_maxi_'
    elif name == 'Stackoverflow (Stack Exchange)':
        if language == 'en':
            url = f'https://download.kiwix.org/zim/stack_exchange/stackoverflow.com_{language}_all_'
        else:
            url = f'https://download.kiwix.org/zim/stack_exchange/{language}.stackoverflow.com_{language}_all_'
    elif name == 'Superuser (Stack Exchange)':
        url = f'https://download.kiwix.org/zim/stack_exchange/superuser.com_{language}_all_'
    elif name == 'iFixit':
        url = f'https://download.kiwix.org/zim/ifixit/ifixit_{language}_all_'
    elif name == 'Gutenberg':
        url = f'https://download.kiwix.org/zim/gutenberg/gutenberg_{language}_all_'
    elif name == 'Amateur Radio (Stack Exchange)':
        url = f'https://download.kiwix.org/zim/stack_exchange/ham.stackexchange.com_{language}_all_'
    elif name == 'DIY (Stack Exchange)':
        url = f'https://download.kiwix.org/zim/stack_exchange/diy.stackexchange.com_{language}_all_'
    elif name == 'Electronics (Stack Exchange)':
        url = f'https://download.kiwix.org/zim/stack_exchange/electronics.stackexchange.com_{language}_all_'
    elif name == 'Unix (Stack Exchange)':
        url = f'https://download.kiwix.org/zim/stack_exchange/unix.stackexchange.com_{language}_all_'
    elif name == 'Ask Ubuntu (Stack Exchange)':
        url = f'https://download.kiwix.org/zim/stack_exchange/askubuntu.com_{language}_all_'
    elif name == 'Bicycles (Stack Exchange)':
        url = f'https://download.kiwix.org/zim/stack_exchange/bicycles.stackexchange.com_{language}_all_'
    elif name == 'Biology (Stack Exchange)':
        url = f'https://download.kiwix.org/zim/stack_exchange/biology.stackexchange.com_{language}_all_'
    elif name == 'Arduino (Stack Exchange)':
        url = f'https://download.kiwix.org/zim/stack_exchange/arduino.stackexchange.com_{language}_all_'
    elif name == '3D Printing (Stack Exchange)':
        url = f'https://download.kiwix.org/zim/stack_exchange/3dprinting.stackexchange.com_{language}_all_'
    elif name == 'MD Wiki (Wiki Project Med Foundation)':
        url = f'https://download.kiwix.org/zim/other/mdwiki_{language}_all_'
    elif name == 'WikiMed Medical Encyclopedia':
        url = f'https://download.kiwix.org/zim/wikipedia/wikipedia_{language}_medicine_'
    elif name == 'Post Disaster Resource Library':
        url = f'https://download.kiwix.org/zim/other/zimgit-post-disaster_{language}_'
    elif name == 'Military Medicine':
        url = f'https://download.kiwix.org/zim/zimit/fas-military-medicine_{language}_'
    elif name == 'WikEm (Global Emergency Medicine Wiki)':
        url = f'https://download.kiwix.org/zim/other/wikem_{language}_all_maxi_'
    elif name == 'Health (Stack Exchange)':
        url = f'https://download.kiwix.org/zim/stack_exchange/health.stackexchange.com_{language}_all_'
    elif name == 'Khan Academy':
        url = f'https://download.kiwix.org/zim/other/khanacademy_{language}_all_'
    else:
        raise ValueError(f'{name} not a valid Kiwix subscription name!')

    if language not in kiwix.KIWIX_CATALOG_BY_NAME[name]['languages']:
        raise ValueError(f'Language {repr(str(language))} is invalid for {name}')

    subscription.change_download(url, frequency, session=session)
    session.add(subscription)
    session.flush([subscription])
    session.commit()
    return subscription


@optional_session
async def unsubscribe(subscription_id: int, session: Session = None):
    subscription: ZimSubscription = session.query(ZimSubscription).filter_by(id=subscription_id).one_or_none()
    if subscription:
        session.delete(subscription)
        if subscription.download:
            session.delete(subscription.download)
        session.commit()
    else:
        raise UnknownZimSubscription(f'{subscription_id=}')


KIWIX_URL_PARSER = re.compile(r'https:\/\/download\.kiwix\.org\/zim\/(.+?)\/(.+?)[_-](\w{2,3})([_-].+)')
KIWIX_URL_NO_FLAVOR_PARSER = re.compile(r'https:\/\/download\.kiwix\.org\/zim\/(.+?)\/(.+)[_-]([a-zA-Z]{2,3})')


def zim_download_url_to_name(url: str) -> Tuple[str, str]:
    try:
        _, project, language, flavor = KIWIX_URL_PARSER.match(url).groups()
    except AttributeError:
        # May not have a "flavor".
        _, project, language = KIWIX_URL_NO_FLAVOR_PARSER.match(url).groups()
        flavor = None
    if project == 'wikipedia' and flavor == '_all_maxi_':
        name = 'Wikipedia (with images)'
    elif project == 'wikipedia' and flavor == '_all_nopic_':
        name = 'Wikipedia (no images)'
    elif project == 'wikipedia' and flavor == '_all_mini_':
        name = 'Wikipedia (mini)'
    elif project == 'wikiversity' and flavor == '_all_maxi_':
        name = 'Wikiversity (with images)'
    elif project == 'wikiversity' and flavor == '_all_nopic_':
        name = 'Wikiversity (no images)'
    elif project == 'wiktionary' and flavor == '_all_maxi_':
        name = 'Wikitionary (with images)'
    elif project == 'wiktionary' and flavor == '_all_nopic_':
        name = 'Wikitionary (no images)'
    elif project == 'wikibooks' and flavor == '_all_maxi_':
        name = 'Wikibooks (with images)'
    elif project == 'wikibooks' and flavor == '_all_nopic_':
        name = 'Wikibooks (no images)'
    elif project == 'wikisource' and flavor == '_all_maxi_':
        name = 'Wikisource'
    elif project == 'raspberrypi.stackexchange.com' and flavor == '_all_':
        name = 'Raspberry Pi (Stack Exchange)'
    elif project == 'vikidia' and flavor == '_all_maxi_':
        name = 'Vikidia'
    elif 'stackoverflow.com' in project and flavor == '_all_':
        name = 'Stackoverflow (Stack Exchange)'
    elif project == 'superuser.com' and flavor == '_all_':
        name = 'Superuser (Stack Exchange)'
    elif project == 'ifixit' and flavor == '_all_':
        name = 'iFixit'
    elif project == 'gutenberg' and flavor == '_all_':
        name = 'Gutenberg'
    elif project == 'ham.stackexchange.com' and flavor == '_all_':
        name = 'Amateur Radio (Stack Exchange)'
    elif project == 'diy.stackexchange.com' and flavor == '_all_':
        name = 'DIY (Stack Exchange)'
    elif project == 'electronics.stackexchange.com' and flavor == '_all_':
        name = 'Electronics (Stack Exchange)'
    elif project == 'unix.stackexchange.com' and flavor == '_all_':
        name = 'Unix (Stack Exchange)'
    elif project == 'askubuntu.com' and flavor == '_all_':
        name = 'Ask Ubuntu (Stack Exchange)'
    elif project == 'bicycles.stackexchange.com' and flavor == '_all_':
        name = 'Bicycles (Stack Exchange)'
    elif project == 'biology.stackexchange.com' and flavor == '_all_':
        name = 'Biology (Stack Exchange)'
    elif project == 'arduino.stackexchange.com' and flavor == '_all_':
        name = 'Arduino (Stack Exchange)'
    elif project == '3dprinting.stackexchange.com' and flavor == '_all_':
        name = '3D Printing (Stack Exchange)'
    elif project == 'mdwiki' and flavor == '_all_':
        name = 'MD Wiki (Wiki Project Med Foundation)'
    elif project == 'wikipedia' and flavor == '_medicine_':
        name = 'WikiMed Medical Encyclopedia'
    elif project == 'zimgit-post-disaster' and flavor is None:
        name = 'Post Disaster Resource Library'
    elif project == 'fas-military-medicine' and flavor is None:
        name = 'Military Medicine'
    elif project == 'wikem' and flavor == '_all_maxi_':
        name = 'WikEm (Global Emergency Medicine Wiki)'
    elif project == 'health.stackexchange.com' and flavor == '_all_':
        name = 'Health (Stack Exchange)'
    elif project == 'khanacademy' and flavor == '_all_':
        name = 'Khan Academy'
    else:
        raise RuntimeError(f'Could not find name for Zim URL: {url} {project=} {flavor=}')

    if language not in kiwix.KIWIX_CATALOG_BY_NAME[name]['languages']:
        raise ValueError(f'Language {repr(str(language))} is invalid for {name}')

    return name, language


def get_zim_directory() -> pathlib.Path:
    zim_directory = get_media_directory() / get_wrolpi_config().zims_destination
    return zim_directory


async def check_zim(path: pathlib.Path) -> int:
    """
    Runs `zimcheck` against the Zim file.  Zim is valid only if this returns `0`.

    @warning: Only performs the checksum check!
    """
    cmd = ('zimcheck', '-C', path.absolute())
    cmd_str = " ".join(str(i) for i in cmd)
    logger.debug(f'check_zim: {cmd_str}')
    result = await run_command(cmd)
    logger.debug(f'zimcheck returned {result.return_code}')
    if result.return_code != 0 and result.stderr:
        logger.debug(result.stderr)
    return result.return_code


ZIM_NAME_PARSER = re.compile(r'(.+?)_(\d{4}-\d{2}).zim')


def parse_name(path: pathlib.Path) -> Tuple[str, datetime]:
    name, date = ZIM_NAME_PARSER.match(path.name).groups()
    date = datetime.strptime(date, '%Y-%m')
    return name, date


def find_outdated_zim_files(path: pathlib.Path = None) -> Tuple[List[pathlib.Path], List[pathlib.Path]]:
    """Search the Zim directory for outdated Zim files.  Returns a list of outdated, and a list of current Zim files."""
    path = path or get_zim_directory()
    if not path.is_dir():
        logger.error(f'Cannot search for outdated Zim files because the directory does not exist: {path}')
        return list(), list()

    # Find all non-empty Zim files.
    files = [i for i in walk(path) if i.is_file() and i.suffix == '.zim' and i.stat().st_size]
    zims = list()
    for file in files:
        try:
            name, date = parse_name(file)
        except Exception as e:
            logger.warning(f'Found Zim {file} but its name does not match.', exc_info=e)
            continue

        zims.append((name, date, file))

    # Order by newest first.
    zims = sorted(zims, key=lambda i: i[1], reverse=True)
    outdated_files = list()
    current_files = list()
    newest_names = list()
    for name, date, file in zims:
        if name in newest_names:
            # Already saw this name, this date is older.
            outdated_files.append(file)
        else:
            newest_names.append(name)
            current_files.append(file)

    return sorted(outdated_files), sorted(current_files)


async def remove_outdated_zim_files(path: pathlib.Path = None) -> int:
    """Deletes all old Zim files."""
    outdated, _ = find_outdated_zim_files(path)
    logger.info(f'Deleting {len(outdated)} outdated Zim files: {outdated}')
    deleted_count = 0
    for file in outdated:
        file.unlink()
        deleted_count += 1

    if PYTEST:
        await refresh_files(outdated)
    else:
        background_task(refresh_files(outdated))

    await restart_kiwix()

    return deleted_count


@register_refresh_cleanup
def flag_outdated_zim_files():
    """Set the `outdated_zims` Flag if outdated Zim files can be found, otherwise clear it."""
    outdated, _ = find_outdated_zim_files()
    if outdated:
        logger.info('Outdated Zims were found')
        flags.outdated_zims.set()
    else:
        logger.info('Outdated Zims were not found')
        flags.outdated_zims.clear()


async def restart_kiwix():
    if PYTEST:
        logger.warning('Unable to restart Kiwix serve because we are testing')
        return
    if DOCKERIZED:
        logger.warning('Setting Kiwix restart because this is in a docker container')
        flags.kiwix_restart.set()
        return

    logger.info('Restarting Kiwix serve')

    cmd = ('sudo', '/usr/bin/systemctl', 'restart' 'wrolpi-kiwix.service')
    result = await run_command(cmd)
    logger.debug(f'systemctl returned {result.return_code}')
    if result.return_code != 0 and result.stderr:
        logger.debug(result.stderr)
    return result.return_code


@optional_session
def set_zim_auto_search(zim_id: int, auto_search: bool, session: Session = None):
    zim = Zim.find_by_id(zim_id, session)
    zim.auto_search = auto_search
    session.commit()
