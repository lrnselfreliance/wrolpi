"""A database config imports by reading its file, diffing it against a snapshot of the database, and writing only the
differences in one short write (see wrolpi.config_import).  download_manager.yaml is the first config to import this
way."""
import sqlite3
import threading
from contextlib import contextmanager
from datetime import timedelta

import pytest
import yaml
from sqlalchemy import event, text
from sqlalchemy.engine import Engine

from modules.zim.models import ZimSubscription
from wrolpi import conftest
from wrolpi.config_version import get_config_version
from wrolpi.dates import now
from wrolpi.db import get_db_session
from wrolpi.downloader import Download, DownloadManagerConfig, get_download_manager_config, import_downloads_config

WRITES = ('INSERT', 'UPDATE', 'DELETE', 'BEGIN IMMEDIATE')
KIWIX_URL = 'https://download.kiwix.org/zim/wikisource/wikisource_en_all_maxi_'


@contextmanager
def statements():
    """Collect the SQL statements run in this block."""
    collected = []

    def collect(conn, cursor, statement, *_):
        collected.append(statement.lstrip())

    event.listen(Engine, 'before_cursor_execute', collect)
    try:
        yield collected
    finally:
        event.remove(Engine, 'before_cursor_execute', collect)


def writes(collected):
    return [i for i in collected if i.upper().startswith(WRITES)]


def database_path(test_session) -> str:
    return test_session.get_bind().url.database


@pytest.fixture
def production_like_sessions(test_session, saved_downloads):
    """Each `get_db_session` gets its own connection, as in production (after `saved_downloads` is committed)."""
    test_session.commit()
    with conftest.production_like_sessions(test_session) as maker:
        yield maker


@pytest.fixture
async def saved_downloads(test_session, test_directory, test_download_manager_config, await_switches):
    """Downloads of every shape download_manager.yaml saves, saved to the config (which records its version)."""
    destination = test_directory / 'videos/channel'
    yesterday = now() - timedelta(days=1)
    test_session.add_all([
        Download(url='https://example.com/once', downloader='archive', status='new'),
        Download(url='https://example.com/recurring', downloader='video_channel', frequency=86400,
                 sub_downloader='video', destination=destination, tag_names=['one', 'two'],
                 settings=dict(video_resolutions=['720p']), last_successful_download=yesterday,
                 next_download=now() + timedelta(days=1), status='complete'),
        Download(url='https://example.com/removed', downloader='rss', frequency=3600, status='new'),
        # Not saved (completed once-downloads count toward the daily limit), so never "removed".
        Download(url='https://example.com/completed', downloader='archive', status='complete',
                 last_successful_download=yesterday),
    ])
    test_session.commit()
    from modules.zim import lib as zim_lib
    await zim_lib.subscribe(test_session, 'Wikisource', 'en')
    test_session.commit()

    get_download_manager_config().dump_config()
    await await_switches()
    assert get_config_version(test_session, 'download_manager.yaml') is not None
    return test_download_manager_config


def edit_config(path, change):
    data = yaml.safe_load(path.read_text())
    change(data)
    path.write_text(yaml.dump(data))


def urls(test_session):
    test_session.expire_all()
    return {i.url for i in test_session.query(Download)}


@pytest.mark.asyncio
async def test_unchanged_import_writes_nothing(test_session, saved_downloads):
    """Importing a config the database already matches opens no write transaction."""
    config = get_download_manager_config()
    with statements() as collected:
        config.import_config()

    assert config.successful_import is True
    assert writes(collected) == []
    # The version, then one snapshot of the Downloads (with their Zim subscriptions).
    assert len(collected) <= 4, collected


@pytest.mark.asyncio
async def test_import_writes_only_the_differences(test_session, saved_downloads):
    """An added Download is inserted, a changed one is updated, a removed one is deleted; the others are untouched.
    Completed once-downloads are not saved, so they are never removed."""
    def change(data):
        downloads = {i['url']: i for i in data['downloads']}
        downloads['https://example.com/recurring']['frequency'] = 604800
        del downloads['https://example.com/removed']
        downloads['https://example.com/added'] = dict(url='https://example.com/added', downloader='archive',
                                                      status='new', last_successful_download=None,
                                                      next_download=None)
        data['downloads'] = list(downloads.values())

    edit_config(saved_downloads, change)
    config = get_download_manager_config()
    with statements() as collected:
        config.import_config()

    assert config.successful_import is True
    assert urls(test_session) == {'https://example.com/once', 'https://example.com/recurring',
                                  'https://example.com/added', 'https://example.com/completed', KIWIX_URL}
    assert Download.get_by_url(test_session, 'https://example.com/recurring').frequency == 604800
    download_writes = [i for i in writes(collected) if ' download' in i.lower()]
    assert len(download_writes) == 3, download_writes


@pytest.mark.asyncio
async def test_zim_subscription_is_restored(test_session, saved_downloads):
    """A Kiwix Download's Zim subscription is derived; a missing one is restored, an existing one is left alone."""
    test_session.query(ZimSubscription).delete()
    test_session.commit()

    get_download_manager_config().import_config()

    subscription = test_session.query(ZimSubscription).one()
    assert (subscription.name, subscription.language, subscription.download.url) == ('Wikisource', 'en', KIWIX_URL)


@pytest.mark.asyncio
async def test_failed_write_changes_nothing(test_session, saved_downloads, production_like_sessions, monkeypatch):
    """The import's changes and its version are one write: a failure leaves neither."""
    from wrolpi.downloader import DownloadsSection
    edit_config(saved_downloads, lambda data: data['downloads'].append(dict(
        url='https://example.com/added', downloader='archive', status='new', last_successful_download=None,
        next_download=None)))
    edit_config(saved_downloads, lambda data: data.update(
        version=data['version'] + 1,
        downloads=[i for i in data['downloads'] if i['url'] != 'https://example.com/removed']))
    before = get_config_version(test_session, 'download_manager.yaml')

    def fail(*args, **kwargs):
        raise RuntimeError('Write failed')

    monkeypatch.setattr(DownloadsSection, 'delete', fail)
    config = get_download_manager_config()
    with pytest.raises(RuntimeError):
        config.import_config()

    assert config.successful_import is False
    assert 'https://example.com/added' not in urls(test_session)
    assert 'https://example.com/removed' in urls(test_session)
    assert get_config_version(test_session, 'download_manager.yaml') == before


@pytest.mark.asyncio
async def test_import_waits_for_a_concurrent_writer(test_session, saved_downloads, production_like_sessions):
    """Another connection holding the write lock delays the import's write; it does not fail it."""
    edit_config(saved_downloads, lambda data: data['downloads'].append(dict(
        url='https://example.com/added', downloader='archive', status='new', last_successful_download=None,
        next_download=None)))
    locked, release = threading.Event(), threading.Event()

    def hold_lock():
        conn = sqlite3.connect(database_path(test_session), isolation_level=None)
        conn.execute('BEGIN IMMEDIATE')
        locked.set()
        release.wait(5)
        conn.execute('COMMIT')
        conn.close()

    thread = threading.Thread(target=hold_lock)
    thread.start()
    locked.wait(5)
    threading.Timer(0.5, release.set).start()
    try:
        get_download_manager_config().import_config()
    finally:
        release.set()
        thread.join()

    with get_db_session() as session:
        assert Download.get_by_url(session, 'https://example.com/added')


@pytest.mark.asyncio
async def test_write_lock_is_free_while_preparing(test_session, saved_downloads, production_like_sessions,
                                                  monkeypatch):
    """Slow preparation (files, network) runs with no transaction open: other writers are not blocked."""
    edit_config(saved_downloads, lambda data: data['downloads'].append(dict(
        url='https://example.com/added', downloader='archive', status='new', last_successful_download=None,
        next_download=None)))
    took_lock = []

    def prepare(self, diffs):
        conn = sqlite3.connect(database_path(test_session), isolation_level=None, timeout=0)
        conn.execute('BEGIN IMMEDIATE')
        conn.execute('COMMIT')
        conn.close()
        took_lock.append(True)

    monkeypatch.setattr(DownloadManagerConfig, 'prepare', prepare)
    get_download_manager_config().import_config()

    assert took_lock == [True]


@pytest.mark.asyncio
async def test_database_change_during_import_is_kept(test_session, saved_downloads, production_like_sessions,
                                                     monkeypatch, await_switches):
    """A Download added after the import read the database (and before it wrote) is not deleted by the older
    file: the import decides again, finds the database newer, and saves it."""
    edit_config(saved_downloads, lambda data: data['downloads'].pop())
    prepared = []

    def prepare(self, diffs):
        if not prepared:
            with get_db_session(commit=True) as session:
                session.add(Download(url='https://example.com/concurrent', downloader='archive', status='new'))
        prepared.append(True)

    monkeypatch.setattr(DownloadManagerConfig, 'prepare', prepare)
    config = get_download_manager_config()
    config.import_config()
    await await_switches()

    assert config.successful_import is True
    with get_db_session() as session:
        assert Download.get_by_url(session, 'https://example.com/concurrent')
    saved = {i['url'] for i in yaml.safe_load(saved_downloads.read_text())['downloads']}
    assert 'https://example.com/concurrent' in saved


@pytest.mark.asyncio
async def test_unknown_version_imports_without_deletes(test_session, saved_downloads, await_switches):
    """Without a database version, a Download the file does not list is kept (and then saved into the file)."""
    test_session.execute(text('DELETE FROM config_version'))
    test_session.commit()
    edit_config(saved_downloads, lambda data: data.update(
        downloads=[i for i in data['downloads'] if i['url'] != 'https://example.com/removed']))

    await import_downloads_config()
    await await_switches()

    assert 'https://example.com/removed' in urls(test_session)
    saved = {i['url'] for i in yaml.safe_load(saved_downloads.read_text())['downloads']}
    assert 'https://example.com/removed' in saved
    assert get_config_version(test_session, 'download_manager.yaml') is not None


@pytest.mark.asyncio
async def test_import_button(test_session, saved_downloads, async_client):
    """The Import button applies the file whatever its version (the user chose it), inside the request's write."""
    test_session.add(Download(url='https://example.com/unsaved', downloader='archive', status='new'))
    test_session.commit()  # The database is now newer than the file.

    request, response = await async_client.post('/api/config/import', json=dict(file_name='download_manager.yaml'))

    assert response.status_code == 204
    assert 'https://example.com/unsaved' not in urls(test_session)


@pytest.mark.asyncio
async def test_relative_destination(test_session, test_directory, saved_downloads):
    """A destination written relative to the media directory is stored absolute, and is then in step."""
    edit_config(saved_downloads, lambda data: data['downloads'].append(dict(
        url='https://example.com/relative', downloader='archive', destination='archive/example.com',
        status='new', last_successful_download=None, next_download=None)))
    config = get_download_manager_config()
    config.import_config()
    test_session.expire_all()
    assert Download.get_by_url(test_session, 'https://example.com/relative').destination \
           == test_directory / 'archive/example.com'

    with statements() as collected:
        config.import_config()
    assert writes(collected) == []


def edit_kiwix(path, **values):
    def change(data):
        for download in data['downloads']:
            if download['url'] == KIWIX_URL:
                download.update(values)

    edit_config(path, change)


@pytest.mark.asyncio
async def test_zim_subscription_follows_a_language_change(test_session, saved_downloads):
    """A Kiwix URL changed to another language moves the existing subscription (its name is unique) to the new
    Download, with the new language; the old Download is removed."""
    french = KIWIX_URL.replace('_en_', '_fr_')
    edit_kiwix(saved_downloads, url=french)

    config = get_download_manager_config()
    config.import_config()

    assert config.successful_import is True
    subscription = test_session.query(ZimSubscription).one()
    assert (subscription.name, subscription.language, subscription.download.url) == ('Wikisource', 'fr', french)
    assert KIWIX_URL not in urls(test_session)


@pytest.mark.asyncio
async def test_zim_subscription_download_keeps_its_state(test_session, saved_downloads):
    """Changing a subscribed Download in the file writes only the file's values: its attempts are kept, and the
    next import is in step."""
    test_session.query(Download).filter_by(url=KIWIX_URL).update(dict(attempts=3))
    test_session.commit()
    edit_kiwix(saved_downloads, frequency=604800)

    config = get_download_manager_config()
    config.import_config()

    test_session.expire_all()
    download = Download.get_by_url(test_session, KIWIX_URL)
    assert (download.frequency, download.attempts) == (604800, 3)
    with statements() as collected:
        config.import_config()
    assert writes(collected) == []


@pytest.mark.asyncio
async def test_unsubscribed_download_drops_its_subscription(test_session, saved_downloads):
    """A Kiwix Download the file keeps, but no longer as recurring, loses its subscription; the next import is in
    step."""
    edit_kiwix(saved_downloads, frequency=None)

    config = get_download_manager_config()
    config.import_config()

    assert test_session.query(ZimSubscription).count() == 0
    assert KIWIX_URL in urls(test_session)
    with statements() as collected:
        config.import_config()
    assert writes(collected) == []


@pytest.mark.asyncio
async def test_unknown_kiwix_url_is_imported(test_session, saved_downloads):
    """A recurring Kiwix URL that names no known subscription is imported as a plain Download; it does not fail the
    other Downloads."""
    unknown = 'https://download.kiwix.org/zim/other/unknown.zim'
    edit_config(saved_downloads, lambda data: data['downloads'].extend([
        dict(url=unknown, downloader='kiwix_zim', frequency=604800, status='new', last_successful_download=None,
             next_download=None),
        dict(url='https://example.com/added', downloader='archive', status='new', last_successful_download=None,
             next_download=None),
    ]))

    config = get_download_manager_config()
    config.import_config()

    assert config.successful_import is True
    assert {unknown, 'https://example.com/added'} <= urls(test_session)
    assert test_session.query(ZimSubscription).count() == 1
    with statements() as collected:
        config.import_config()
    assert writes(collected) == []


@pytest.mark.asyncio
async def test_nothing_to_write_skips_prepare(test_session, saved_downloads, monkeypatch):
    """An import with no differences does not start any preparation."""
    prepared = []
    monkeypatch.setattr(DownloadManagerConfig, 'prepare', lambda self, diffs: prepared.append(diffs))

    get_download_manager_config().import_config()

    assert prepared == []


@pytest.mark.asyncio
async def test_unknown_tag_names_are_dropped(test_session, saved_downloads, test_tags_config, tag_factory,
                                             await_switches):
    """Once tags.yaml is imported, a Tag name the file gives a Download that no Tag has (the Tag was removed) is
    dropped, and the file is saved without it: the next import writes nothing."""
    from wrolpi.tags import get_tags_config
    await tag_factory('one')
    test_session.commit()
    get_tags_config().dump_config()
    get_tags_config().import_config()
    assert get_tags_config().successful_import is True

    def change(data):
        for download in data['downloads']:
            if download['url'] == 'https://example.com/recurring':
                download['tag_names'] = ['one', 'gone']
                download['settings'] = dict(download.get('settings') or {}, channel_tag_name=['gone'])

    edit_config(saved_downloads, change)
    config = get_download_manager_config()
    config.import_config()
    await await_switches()

    test_session.expire_all()
    download = Download.get_by_url(test_session, 'https://example.com/recurring')
    assert download.tag_names == ['one']
    assert download.settings['channel_tag_name'] == []
    with statements() as collected:
        config.import_config()
    assert writes(collected) == []
