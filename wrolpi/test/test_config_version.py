"""A database config's file and the database each carry a version (see wrolpi.config_version)."""
import ast
import inspect
import textwrap
import threading
from copy import deepcopy

import pytest
import yaml

from wrolpi.collections.models import Collection
from wrolpi.config_version import get_config_version, set_config_version
from wrolpi.dates import now
from wrolpi.files.models import FileGroup
from wrolpi.tags import Tag, get_tags_config, import_tags_config
from wrolpi.test.common import config_classes


def write_tags_config(path, version: int, names):
    path.write_text(yaml.dump(dict(version=version, tags={i: dict(color='#000000') for i in names},
                                   tag_files=[], tag_zims=[])))


def db_version(session, name='tags.yaml'):
    session.commit()
    return get_config_version(session, name)


@pytest.mark.asyncio
async def test_owned_changes_count(test_session, test_directory, make_files_structure, async_client):
    """Changing rows a config owns adds one to its database version; other changes do not."""
    set_config_version(test_session, 'tags.yaml', 5)
    set_config_version(test_session, 'domains.yaml', 5)
    set_config_version(test_session, 'channels.yaml', 5)
    set_config_version(test_session, 'recently_viewed.yaml', 5)
    test_session.commit()

    test_session.add(Tag(name='one', color='#000000'))
    test_session.flush()
    assert db_version(test_session) == 6

    # A domain Collection belongs to domains.yaml, not channels.yaml.
    test_session.add(Collection(name='example.com', kind='domain'))
    test_session.flush()
    assert db_version(test_session, 'domains.yaml') == 6
    assert db_version(test_session, 'channels.yaml') == 5

    # recently_viewed.yaml owns only a FileGroup's viewing columns.
    make_files_structure(['a.txt'])
    file_group = FileGroup.from_paths(test_session, test_directory / 'a.txt')
    test_session.add(file_group)
    test_session.flush()
    test_session.commit()
    file_group.title = 'Retitled'
    test_session.flush()
    assert db_version(test_session, 'recently_viewed.yaml') == 5
    file_group.set_viewed()
    test_session.flush()
    assert db_version(test_session, 'recently_viewed.yaml') == 6

    # A config without a database row is not created by a change; its next import creates it.
    test_session.add(Collection(name='Mix', kind='playlist'))
    test_session.flush()
    assert db_version(test_session, 'playlists.yaml') is None


@pytest.mark.asyncio
async def test_dump_writes_database_version(test_session, test_tags_config, await_switches):
    """A saved config carries the database's version, read with the rows it saves."""
    test_session.add(Tag(name='one', color='#000000'))
    test_session.commit()
    set_config_version(test_session, 'tags.yaml', 41)
    test_session.commit()

    config = get_tags_config()
    config.successful_import = True
    config.dump_config()
    await await_switches()
    assert yaml.safe_load(test_tags_config.read_text())['version'] == 41


@pytest.mark.asyncio
async def test_unsaved_database_change_is_saved_not_undone(test_session, test_tags_config, await_switches):
    """WROLPi restarted after a Tag was created, before tags.yaml was saved: the import saves the database instead
    of importing the older file (which would delete the new Tag)."""
    test_session.add(Tag(name='old', color='#000000'))
    test_session.commit()
    write_tags_config(test_tags_config, 3, ['old'])
    set_config_version(test_session, 'tags.yaml', 3)
    test_session.add(Tag(name='new', color='#000000'))  # Counted: the database is now version 4.
    test_session.commit()
    assert db_version(test_session) == 4

    import_tags_config()
    await await_switches()

    assert {i.name for i in test_session.query(Tag)} == {'old', 'new'}
    saved = yaml.safe_load(test_tags_config.read_text())
    assert set(saved['tags']) == {'old', 'new'} and saved['version'] == 4


@pytest.mark.asyncio
@pytest.mark.parametrize('file_version', [3, 9])
async def test_current_file_imports_with_deletes(test_session, test_tags_config, file_version, async_client):
    """A file as new as the database (or newer) is the truth: what it no longer lists is deleted.  The database
    records the file's version."""
    test_session.add_all([Tag(name='kept', color='#000000'), Tag(name='removed', color='#000000')])
    test_session.commit()
    set_config_version(test_session, 'tags.yaml', 3)
    test_session.commit()
    write_tags_config(test_tags_config, file_version, ['kept'])

    import_tags_config()

    assert {i.name for i in test_session.query(Tag)} == {'kept'}
    assert db_version(test_session) == file_version


@pytest.mark.asyncio
async def test_unknown_database_version_imports_without_deletes(test_session, test_tags_config, await_switches):
    """A config this code never imported (no database row) imports without deleting.  The database may keep rows
    the file does not list, so the file's version is not recorded (the next import would delete them); they are
    saved into the file instead, and that save records the version."""
    test_session.add_all([Tag(name='kept', color='#000000'), Tag(name='unlisted', color='#000000')])
    test_session.commit()
    write_tags_config(test_tags_config, 7, ['kept', 'added'])

    import_tags_config()
    assert {i.name for i in test_session.query(Tag)} == {'kept', 'unlisted', 'added'}
    assert db_version(test_session) is None

    await await_switches()
    saved = yaml.safe_load(test_tags_config.read_text())
    assert set(saved['tags']) == {'kept', 'unlisted', 'added'} and saved['version'] == 8
    assert db_version(test_session) == 8


@pytest.mark.asyncio
async def test_failed_import_changes_nothing(test_session, test_tags_config, monkeypatch, async_client):
    """An import that fails partway writes nothing: neither its rows nor the file's version (which would mark a
    partial database as up to date)."""
    from wrolpi.tags import TagsConfig, TagZimsSection

    test_session.add(Tag(name='kept', color='#000000'))
    test_session.commit()
    set_config_version(test_session, 'tags.yaml', 3)
    test_session.commit()
    write_tags_config(test_tags_config, 4, ['kept', 'added'])

    def fail(*args, **kwargs):
        raise RuntimeError('Import failed')

    # Fails after the Tags were written.
    monkeypatch.setattr(TagZimsSection, 'upsert', fail)
    monkeypatch.setattr(TagZimsSection, 'file_rows', lambda self, config: ({('kept', 'a.zim', 'home'): {}}, set()))
    monkeypatch.setattr(TagsConfig, 'prepare', lambda self, diffs: None)
    with pytest.raises(RuntimeError):
        import_tags_config()

    test_session.expire_all()
    assert {i.name for i in test_session.query(Tag)} == {'kept'}
    assert db_version(test_session) == 3


@pytest.mark.asyncio
async def test_import_button_imports_an_older_file(test_session, test_tags_config, async_client):
    """The Import button applies the file whatever its version: the user chose it."""
    test_session.add_all([Tag(name='kept', color='#000000'), Tag(name='removed', color='#000000')])
    test_session.commit()
    set_config_version(test_session, 'tags.yaml', 10)
    test_session.commit()
    write_tags_config(test_tags_config, 2, ['kept'])

    get_tags_config().import_forced()

    assert {i.name for i in test_session.query(Tag)} == {'kept'}
    assert db_version(test_session) == 2


@pytest.mark.asyncio
async def test_raw_writes_count(test_session, test_directory, make_files_structure, async_client):
    """Writes that bypass the ORM flush count their changes explicitly."""
    from wrolpi.downloader import Download, DownloadManager, DownloadStatus
    from wrolpi.files.lib import _bulk_delete_tag_files, _bulk_insert_tag_files

    make_files_structure(['a.txt'])
    file_group = FileGroup.from_paths(test_session, test_directory / 'a.txt')
    tag = Tag(name='one', color='#000000')
    test_session.add_all([file_group, tag])
    test_session.commit()
    set_config_version(test_session, 'tags.yaml', 1)
    test_session.commit()

    _bulk_insert_tag_files([(tag.id, file_group.id)])
    assert db_version(test_session) == 2
    _bulk_delete_tag_files([(tag.id, file_group.id)])
    assert db_version(test_session) == 3

    # Untagging deletes in bulk.
    file_group.add_tag(test_session, tag.id)
    test_session.commit()
    assert db_version(test_session) == 4
    file_group.untag(test_session, tag.id)
    test_session.commit()
    assert db_version(test_session) == 5

    # Retrying Downloads updates their status in bulk.
    test_session.add(Download(url='https://example.com/1', status=DownloadStatus.failed))
    test_session.commit()
    set_config_version(test_session, 'download_manager.yaml', 1)
    test_session.commit()
    DownloadManager.retry_downloads(test_session)
    test_session.commit()
    assert db_version(test_session, 'download_manager.yaml') == 2


def test_downloads_count_for_their_collections_config_only(test_session):
    """A Channel's Download is saved by channels.yaml, not repos.yaml: counting it for repos.yaml would make the repos
    import save instead of import."""
    from wrolpi.downloader import Download

    channel = Collection(name='Channel', kind='channel')
    test_session.add(channel)
    test_session.commit()
    for name in ('channels.yaml', 'repos.yaml', 'download_manager.yaml'):
        set_config_version(test_session, name, 1)
    test_session.commit()

    test_session.add(Download(url='https://example.com/channel', frequency=86400, collection_id=channel.id))
    test_session.commit()

    assert db_version(test_session, 'channels.yaml') == 2
    assert db_version(test_session, 'download_manager.yaml') == 2
    assert db_version(test_session, 'repos.yaml') == 1


def test_download_leaving_a_collection_counts_for_its_config(test_session):
    """Moving a Download out of a Channel changes channels.yaml: otherwise its next import would put it back."""
    from wrolpi.downloader import Download

    channel = Collection(name='Channel', kind='channel')
    test_session.add(channel)
    test_session.commit()
    download = Download(url='https://example.com/channel', frequency=86400, collection_id=channel.id)
    test_session.add(download)
    test_session.commit()
    set_config_version(test_session, 'channels.yaml', 1)
    test_session.commit()

    download.collection_id = None
    test_session.commit()

    assert db_version(test_session, 'channels.yaml') == 2


def test_deleting_once_downloads_counts_for_download_manager_only(test_session, test_download_manager):
    """Deleting a once-download (no Collection) does not change channels.yaml or repos.yaml: counting it would make
    their next import save instead of import."""
    from wrolpi.downloader import Download

    download = Download(url='https://example.com/once')
    test_session.add(download)
    test_session.commit()
    for name in ('channels.yaml', 'repos.yaml', 'download_manager.yaml'):
        set_config_version(test_session, name, 1)
    test_session.commit()

    test_download_manager.delete_downloads_by_ids(test_session, [download.id])

    assert db_version(test_session, 'download_manager.yaml') == 2
    assert db_version(test_session, 'channels.yaml') == 1
    assert db_version(test_session, 'repos.yaml') == 1


def test_only_playlist_items_count_for_playlists(test_session):
    """Author and subject Collections have items too; only a playlist's are saved by playlists.yaml."""
    author = Collection(name='Author', kind='author')
    playlist = Collection(name='Mix', kind='playlist')
    test_session.add_all([author, playlist])
    test_session.commit()
    set_config_version(test_session, 'playlists.yaml', 1)
    test_session.commit()

    author.add_url(test_session, '/map?x=1', title='Spot')
    test_session.commit()
    assert db_version(test_session, 'playlists.yaml') == 1

    playlist.add_url(test_session, '/map?x=1', title='Spot')
    test_session.commit()
    assert db_version(test_session, 'playlists.yaml') == 2


def test_unsaved_columns_do_not_count(test_session):
    """Columns a config does not save (a fetch's commit, a refresh's counts, a download attempt) do not count:
    counting them would make that config's next import save instead of import."""
    from modules.repos.models import Repository
    from modules.videos.models import Channel
    from wrolpi.downloader import Download

    channel_collection = Collection(name='Channel', kind='channel')
    repo_collection = Collection(name='Repo', kind='repo')
    test_session.add_all([channel_collection, repo_collection])
    test_session.flush()
    channel = Channel(collection_id=channel_collection.id)
    repo = Repository(url='https://example.com/repo.git', collection_id=repo_collection.id)
    download = Download(url='https://example.com/channel', frequency=86400, collection_id=channel_collection.id)
    test_session.add_all([channel, repo, download])
    test_session.commit()
    names = ('channels.yaml', 'repos.yaml', 'download_manager.yaml')
    for name in names:
        set_config_version(test_session, name, 1)
    test_session.commit()

    repo.head_sha = 'abc123'
    repo.last_fetch = now()
    channel.video_count = 10
    channel.refreshed = True
    channel_collection.item_count = 10
    repo_collection.total_size = 1000
    download.attempts = 1
    download.error = 'Failed'
    download.last_download_attempt = now()
    test_session.commit()
    assert {i: db_version(test_session, i) for i in names} == dict.fromkeys(names, 1)

    # Saved columns still count.
    repo.branch = 'dev'
    channel.generate_posters = True
    download.status = 'failed'
    test_session.commit()
    assert {i: db_version(test_session, i) for i in names} == dict.fromkeys(names, 2)


def test_domain_downloads_count_for_domains(test_session):
    """domains.yaml saves each domain's Downloads (url, frequency)."""
    from wrolpi.downloader import Download

    domain = Collection(name='example.com', kind='domain')
    test_session.add(domain)
    test_session.commit()
    set_config_version(test_session, 'domains.yaml', 1)
    test_session.commit()

    test_session.add(Download(url='https://example.com/feed', frequency=86400, collection_id=domain.id))
    test_session.commit()

    assert db_version(test_session, 'domains.yaml') == 2


@pytest.mark.parametrize('config_class', [i for i in config_classes() if getattr(i, 'sections', None)],
                         ids=lambda i: i.__name__)
@pytest.mark.asyncio
async def test_import_while_another_process_initializes(test_session, test_directory, async_client,
                                                        restore_switch_handlers, config_class, monkeypatch):
    """The Sanic processes initialize the configs they share while one of them imports the database configs.  The
    import records the version of the file it read, whatever another process does to the shared config meanwhile;
    otherwise the database's version goes back (e.g. to 0), and every later save is refused as older than the file."""
    config = config_class()
    file = config.get_file()
    file.parent.mkdir(parents=True, exist_ok=True)
    config.write_config_data({**deepcopy(config.default_config), 'version': 7}, file)
    shared = dict()
    config.initialize(shared)
    set_config_version(test_session, config.file_name, 7)
    test_session.commit()
    # Configs refuse to import while testing unless they are the test's config.
    monkeypatch.setattr('wrolpi.tags.TEST_TAGS_CONFIG', config)
    monkeypatch.setattr('modules.videos.lib.TEST_CHANNELS_CONFIG', config)

    # Another process initializes this config, and pauses if it reads the file.
    other_process = threading.Thread(target=config.initialize, args=(shared,))
    paused, resume = threading.Event(), threading.Event()
    read_config_file = config.read_config_file

    def pausing_read_config_file(*args, **kwargs):
        if threading.current_thread() is other_process:
            paused.set()
            resume.wait(10)
        return read_config_file(*args, **kwargs)

    monkeypatch.setattr(config, 'read_config_file', pausing_read_config_file)

    # It starts after this import has decided what to do, and before it writes.
    version_decision = config.version_decision

    def racing_version_decision(*args, **kwargs):
        decision = version_decision(*args, **kwargs)
        other_process.start()
        while other_process.is_alive() and not paused.wait(0.01):
            pass
        return decision

    monkeypatch.setattr(config, 'version_decision', racing_version_decision)
    try:
        config.import_config()
    finally:
        resume.set()
        if other_process.is_alive():
            other_process.join(10)

    assert config.successful_import
    assert db_version(test_session, config.file_name) == 7


@pytest.mark.parametrize('config_class', [i for i in config_classes() if getattr(i, 'sections', None)],
                         ids=lambda i: i.__name__)
def test_import_steps_read_the_file(config_class):
    """`prepare` and `after_import` (and the methods they call) read the file's config (`import_file_config`), never
    the shared `_config`, which other processes change during the import."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(config_class)))
    methods = {i.name: i for i in tree.body[0].body if isinstance(i, ast.FunctionDef)}
    properties = {name for name, method in methods.items()
                  if any(getattr(i, 'id', None) == 'property' for i in method.decorator_list)}
    reads, seen, todo = set(), set(), [i for i in ('prepare', 'after_import') if i in methods]
    while todo:
        if (name := todo.pop()) in seen:
            continue
        seen.add(name)
        for node in ast.walk(methods[name]):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == 'self':
                if node.attr in methods and node.attr not in properties:
                    todo.append(node.attr)
                elif node.attr in properties | {'_config', 'version'}:
                    reads.add(f'{name} reads self.{node.attr}')
    assert not reads
