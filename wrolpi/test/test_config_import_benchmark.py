"""Benchmark every database config import, as WROLPi runs them at startup.

Skipped unless WROLPI_CONFIG_BENCH=1.  WROLPI_CONFIG_BENCH_SCALE (default 1) multiplies every row count.

    WROLPI_CONFIG_BENCH=1 pytest -s -p no:randomly wrolpi/test/test_config_import_benchmark.py

Each config's rows are inserted directly, then written to YAML by that config's own `dump_config`, so the
files are exactly what WROLPi would save.  Two passes are timed, in startup order:

* steady: the database already matches every config (a normal restart).
* rebuild: the config-owned rows are deleted, then every config is imported (restoring onto a fresh database).

For each import it prints wall time and the number of SQL statements it ran.
"""
import os
import time
from contextlib import contextmanager
from datetime import timedelta

import mock
import pytest
from sqlalchemy import event, text
from sqlalchemy.engine import Engine

from wrolpi.dates import now

pytestmark = pytest.mark.skipif(os.environ.get('WROLPI_CONFIG_BENCH') != '1',
                                reason='Set WROLPI_CONFIG_BENCH=1 to run the config import benchmark')

SCALE = float(os.environ.get('WROLPI_CONFIG_BENCH_SCALE', '1'))


def n(count: int) -> int:
    return max(1, int(count * SCALE))


TAGS, TAG_FILES, DOWNLOADS, CHANNELS, DOMAINS, PLAYLISTS, PLAYLIST_ITEMS, REPOS, VIEWED = \
    n(50), n(5_000), n(2_000), n(500), n(500), n(100), n(200), n(200), n(1_000)


@contextmanager
def measure(results: list, label: str):
    statements = []

    def count(conn, cursor, statement, *_):
        if not statement.lstrip().upper().startswith(('BEGIN', 'COMMIT', 'ROLLBACK', 'SAVEPOINT', 'RELEASE')):
            statements.append(statement)

    # Every engine: production_like_sessions makes its own.
    event.listen(Engine, 'before_cursor_execute', count)
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        event.remove(Engine, 'before_cursor_execute', count)
        writes = sum(1 for i in statements if i.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')))
        results.append((label, elapsed, len(statements), writes))


def build_library(session, test_directory):
    """Insert every config-owned row, in bulk."""
    from modules.repos.models import Repository
    from modules.videos.models import Channel
    from wrolpi.collections.models import Collection, CollectionItem
    from wrolpi.downloader import Download
    from wrolpi.files.models import FileGroup
    from wrolpi.tags import Tag, TagFile

    tags = [Tag(name=f'tag{i}', color='#000000') for i in range(TAGS)]
    session.add_all(tags)

    files_directory = test_directory / 'bench'
    file_groups = list()
    for i in range(TAG_FILES):
        directory = files_directory / f'd{i // 500}'
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f'file{i}.txt'
        path.write_text(str(i))
        file_groups.append(FileGroup(primary_path=path, directory=directory, stem=f'file{i}', suffix='.txt',
                                     mimetype='text/plain', size=1,
                                     files=[{'path': path.name, 'mimetype': 'text/plain', 'size': 1}]))
    for i, file_group in enumerate(file_groups[:VIEWED]):
        file_group.viewed = now() - timedelta(minutes=i)
        file_group.progress = 0.5
    session.add_all(file_groups)
    session.flush()
    session.add_all([TagFile(tag_id=tags[i % TAGS].id, file_group_id=fg.id) for i, fg in enumerate(file_groups)])

    session.add_all([Download(url=f'https://example.com/once/{i}', downloader='archive', status='new')
                     for i in range(DOWNLOADS)])

    for i in range(CHANNELS):
        directory = test_directory / f'videos/channel{i}'
        collection = Collection(name=f'channel{i}', kind='channel', directory=directory)
        session.add(collection)
        session.flush()
        url = f'https://example.com/channel/{i}'
        session.add(Channel(name=f'channel{i}', collection_id=collection.id, directory=directory, url=url,
                            source_id=f'source{i}'))
        session.add(Download(url=f'{url}/videos', downloader='video_channel', frequency=604800, status='new',
                             collection_id=collection.id, destination=directory))

    session.add_all([Collection(name=f'domain{i}.example.com', kind='domain') for i in range(DOMAINS)])

    for i in range(PLAYLISTS):
        playlist = Collection(name=f'playlist{i}', kind='playlist')
        session.add(playlist)
        session.flush()
        session.add_all([CollectionItem(collection_id=playlist.id, item_kind='url', url=f'/url/{i}/{j}',
                                        title=f'item {j}', position=j + 1) for j in range(PLAYLIST_ITEMS)])

    for i in range(REPOS):
        url = f'https://git.example.com/owner/repo{i}'
        collection = Collection(name=f'repo{i}', kind='repo', directory=test_directory / f'repos/repo{i}')
        session.add(collection)
        session.flush()
        session.add(Repository(url=url, collection_id=collection.id, mode='full', clone_token=f'{i:032d}'))

    session.commit()


CONFIG_FILES = ('tags.yaml', 'download_manager.yaml', 'channels.yaml', 'domains.yaml', 'playlists.yaml',
                'repos.yaml', 'recently_viewed.yaml')


def dump_all():
    from modules.archive.lib import get_domains_config
    from modules.repos.lib import get_repos_config
    from modules.videos.lib import get_channels_config
    from wrolpi.collections.config import get_playlists_config
    from wrolpi.downloader import get_download_manager_config
    from wrolpi.files.progress import get_recently_viewed_config
    from wrolpi.tags import get_tags_config

    for config in (get_tags_config(), get_download_manager_config(), get_channels_config(), get_domains_config(),
                   get_playlists_config(), get_repos_config(), get_recently_viewed_config()):
        config.successful_import = True
        config.dump_config(overwrite=True)


async def import_all(results: list, prefix: str):
    """Import every database config in startup order (see `import_all_db_configs`)."""
    from modules.archive.lib import import_domains_config
    from modules.repos.lib import import_repos_config
    from modules.videos.lib import import_channels_config
    from wrolpi.collections.config import get_playlists_config
    from wrolpi.downloader import get_download_manager_config
    from wrolpi.files.progress import get_recently_viewed_config
    from wrolpi.tags import import_tags_config

    steps = [
        ('tags', import_tags_config),
        ('downloads', get_download_manager_config().import_config),
        ('channels', import_channels_config),
        ('domains', import_domains_config),
        ('playlists', get_playlists_config().import_config),
        ('repos', import_repos_config),
        ('recently_viewed', get_recently_viewed_config().import_config),
    ]
    for name, step in steps:
        with measure(results, f'{prefix} {name}'):
            step()


def wipe_config_rows(session):
    for table in ('tag_file', 'collection_item', 'channel', 'repository', 'download', 'collection', 'tag',
                  'config_version'):
        session.execute(text(f'DELETE FROM {table}'))
    session.execute(text('UPDATE file_group SET viewed = NULL, progress = NULL, position = NULL'))
    session.commit()


def assert_imported(session):
    """Every config-owned row is back, so each timed import did its work."""
    expected = {
        'SELECT COUNT(*) FROM tag': TAGS,
        'SELECT COUNT(*) FROM tag_file': TAG_FILES,
        "SELECT COUNT(*) FROM collection WHERE kind = 'channel'": CHANNELS,
        'SELECT COUNT(*) FROM channel': CHANNELS,
        "SELECT COUNT(*) FROM collection WHERE kind = 'domain'": DOMAINS,
        "SELECT COUNT(*) FROM collection WHERE kind = 'playlist'": PLAYLISTS,
        'SELECT COUNT(*) FROM collection_item': PLAYLISTS * PLAYLIST_ITEMS,
        'SELECT COUNT(*) FROM repository': REPOS,
        'SELECT COUNT(*) FROM file_group WHERE viewed IS NOT NULL': VIEWED,
        "SELECT COUNT(*) FROM download WHERE url LIKE 'https://example.com/once/%'": DOWNLOADS,
    }
    actual = {sql: session.execute(text(sql)).scalar() for sql in expected}
    assert actual == expected


def report(results: list):
    counts = dict(tags=TAGS, tag_files=TAG_FILES, downloads=DOWNLOADS, channels=CHANNELS, domains=DOMAINS,
                  playlists=PLAYLISTS, playlist_items=PLAYLIST_ITEMS, repos=REPOS, viewed=VIEWED)
    print(f'\nConfig import benchmark (scale {SCALE}): {counts}')
    print(f'{"import":<26}{"seconds":>10}{"statements":>12}{"writes":>9}')
    for label, elapsed, statements, writes in results:
        print(f'{label:<26}{elapsed:>10.3f}{statements:>12}{writes:>9}')
    for prefix in ('steady', 'rebuild'):
        total = sum(i[1] for i in results if i[0].startswith(prefix))
        print(f'{prefix + " total":<26}{total:>10.3f}')


@pytest.mark.asyncio
@pytest.mark.timeout(1800)  # A Pi takes minutes at scale 1; pytest.ini's 120s is a hang detector.
async def test_config_import_benchmark(test_session, test_directory, async_client, test_wrolpi_config,
                                       test_tags_config, test_download_manager_config, test_channels_config,
                                       await_switches, await_background_tasks):
    from wrolpi.conftest import production_like_sessions
    from wrolpi.downloader import download_manager

    build_library(test_session, test_directory)
    dump_all()
    # `dump_config` updates the config in memory; a switch writes the file.
    await await_switches()
    missing = [i for i in CONFIG_FILES if not (test_directory / 'config' / i).is_file()]
    assert not missing, f'Configs were not written: {missing}'
    results = list()

    try:
        with production_like_sessions(test_session), \
                mock.patch.object(download_manager, 'dispatch_downloads', mock.AsyncMock()):
            await import_all(results, 'steady')
            # Imports start switches and background tasks; let them finish before the next pass.
            await await_background_tasks()
            await await_switches()
        test_session.rollback()
        wipe_config_rows(test_session)
        with production_like_sessions(test_session), \
                mock.patch.object(download_manager, 'dispatch_downloads', mock.AsyncMock()):
            await import_all(results, 'rebuild')
            await await_background_tasks()
            await await_switches()
        test_session.rollback()
        assert_imported(test_session)
    finally:
        report(results)
