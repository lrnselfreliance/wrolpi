"""Tests for PlaylistsConfig disaster recovery: a missing or empty playlists.yaml must never
delete playlists from the database (mirroring ChannelsConfig's guards)."""
from copy import deepcopy

import pytest

from wrolpi.collections.config import get_playlists_config
from wrolpi.collections.models import Collection


@pytest.fixture
def playlists_config(async_client):
    """The global playlists config, reset to defaults (it is not reset by
    initialize_configs_contexts like other configs)."""
    config = get_playlists_config()
    config._config = deepcopy(config.default_config)
    return config


def _make_playlist(session, name='Survives'):
    collection = Collection(name=name, kind='playlist')
    session.add(collection)
    collection.add_url(session, '/map?lat=1&lon=2&z=3', title='spot')
    session.commit()
    return collection


@pytest.mark.asyncio
async def test_import_missing_config_preserves_db(test_session, test_directory, playlists_config):
    """If playlists.yaml does not exist, importing must NOT delete playlists from the DB.

    A missing config (partial restore, fresh config directory, disk problem) is not the same as
    an explicit "no playlists"; deleting here would cascade into the on-disk sync pruning the
    playlist directories and the next dump writing an empty config -- total, permanent loss.
    """
    _make_playlist(test_session)
    assert not playlists_config.get_file().is_file()

    playlists_config.import_config()

    test_session.expire_all()
    collection = test_session.query(Collection).filter_by(kind='playlist').one()
    assert collection.name == 'Survives'
    assert len(collection.items) == 1
    # Nothing to import is a successful import (matches ChannelsConfig).
    assert playlists_config.successful_import is True


@pytest.mark.asyncio
async def test_import_empty_config_preserves_db(test_session, test_directory, playlists_config):
    """A config file with an empty (or absent) playlists list must NOT delete DB playlists.

    Matches ChannelsConfig: an empty list never deletes DB records.  Deleting all playlists is
    done through the UI/API, which dumps the (empty) config itself.
    """
    _make_playlist(test_session)

    file = playlists_config.get_file()
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text('version: 1\nplaylists: []\n')

    playlists_config.import_config()

    test_session.expire_all()
    collection = test_session.query(Collection).filter_by(kind='playlist').one()
    assert collection.name == 'Survives'
    assert playlists_config.successful_import is True


@pytest.mark.asyncio
async def test_db_rebuild_round_trip(test_session, test_directory, playlists_config):
    """After a full DB rebuild, playlists are recovered from playlists.yaml.

    File items can only be re-linked after the file refresh has re-indexed their FileGroups; until
    then they are skipped with a warning, and restored by a later re-import (the config file still
    holds them as media-relative paths).
    """
    from wrolpi.files.models import FileGroup

    pdf = test_directory / 'guide.pdf'
    pdf.write_bytes(b'%PDF-1.4 x')
    file_group = FileGroup.from_paths(test_session, pdf)
    collection = Collection(name='Rebuild', kind='playlist')
    test_session.add(collection)
    test_session.flush([collection])
    collection.add_file_group(file_group, session=test_session)
    collection.add_url(test_session, '/map?x=1', title='Spot')
    test_session.commit()

    playlists_config.dump_config()

    # Simulate a DB rebuild: collections AND file groups are gone.
    test_session.query(Collection).filter_by(kind='playlist').delete()
    test_session.query(FileGroup).delete()
    test_session.commit()

    playlists_config.import_config()
    test_session.expire_all()
    collection = test_session.query(Collection).filter_by(name='Rebuild', kind='playlist').one()
    # The file is not indexed yet, so only the url item could be restored.
    assert [i.item_kind for i in collection.items] == ['url']

    # The file refresh re-indexes the file; a re-import restores the file item in its position.
    FileGroup.from_paths(test_session, pdf)
    test_session.commit()
    playlists_config.import_config()
    test_session.expire_all()
    collection = test_session.query(Collection).filter_by(name='Rebuild', kind='playlist').one()
    assert [i.item_kind for i in collection.items] == ['file', 'url']
    assert [i.position for i in collection.items] == [1, 2]


@pytest.mark.asyncio
async def test_global_refresh_restores_skipped_playlist_items(
        test_session, test_directory, playlists_config, refresh_files, await_switches):
    """A global refresh re-imports playlists.yaml, restoring items skipped at startup.

    After a DB rebuild, playlists.yaml is imported before any files are indexed, so file items are
    skipped.  When the global refresh completes, the worker re-imports the config and the skipped
    items are restored.
    """
    pdf = test_directory / 'guide.pdf'
    pdf.write_bytes(b'%PDF-1.4 x')

    file = playlists_config.get_file()
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(
        'version: 1\n'
        'playlists:\n'
        '  - name: Rebuilt\n'
        '    items:\n'
        '      - file: guide.pdf\n'
        '      - url: /map?x=1\n'
    )

    # Startup import: the file is not indexed yet, so only the url item is restored.
    playlists_config.import_config()
    test_session.expire_all()
    collection = test_session.query(Collection).filter_by(name='Rebuilt', kind='playlist').one()
    assert [i.item_kind for i in collection.items] == ['url']

    # A global refresh indexes the file and triggers the re-import.
    await refresh_files()
    await await_switches()
    test_session.expire_all()

    collection = test_session.query(Collection).filter_by(name='Rebuilt', kind='playlist').one()
    assert [i.item_kind for i in collection.items] == ['file', 'url']
    assert [i.position for i in collection.items] == [1, 2]


@pytest.mark.asyncio
async def test_backup_preview_and_import_merge(test_session, test_directory, playlists_config):
    """A backup can be previewed and merged: backup-only playlists are added, current ones win."""
    file = playlists_config.get_file()
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(
        'version: 3\n'
        'playlists:\n'
        '  - name: Current\n'
        '    items:\n'
        '      - url: /u/current\n'
    )
    backup = playlists_config._get_backup_file('20260101')
    backup.parent.mkdir(parents=True, exist_ok=True)
    backup.write_text(
        'version: 1\n'
        'playlists:\n'
        '  - name: Current\n'
        '    items:\n'
        '      - url: /u/old\n'
        '  - name: Restored\n'
        '    items:\n'
        '      - url: /u/restored\n'
        '      - url: /u/restored2\n'
    )

    preview = playlists_config.preview_backup_import('20260101', 'merge')
    assert preview['add'] == [dict(type='playlist', name='Restored', items=2)]
    assert preview['remove'] == []
    assert preview['unchanged'] == 1

    playlists_config.import_backup('20260101', 'merge')
    test_session.expire_all()
    by_name = {c.name: c for c in test_session.query(Collection).filter_by(kind='playlist').all()}
    assert sorted(by_name) == ['Current', 'Restored']
    # Merge keeps the current config's version of 'Current'.
    assert [i.url for i in by_name['Current'].items] == ['/u/current']
    assert [i.url for i in by_name['Restored'].items] == ['/u/restored', '/u/restored2']


@pytest.mark.asyncio
async def test_backup_preview_and_import_overwrite(test_session, test_directory, playlists_config):
    """Overwrite mode replaces the config (and DB) with the backup's playlists."""
    _make_playlist(test_session, name='CurrentOnly')
    playlists_config.dump_config()

    backup = playlists_config._get_backup_file('20260101')
    backup.parent.mkdir(parents=True, exist_ok=True)
    backup.write_text(
        'version: 1\n'
        'playlists:\n'
        '  - name: FromBackup\n'
        '    items:\n'
        '      - url: /u/backup\n'
    )

    preview = playlists_config.preview_backup_import('20260101', 'overwrite')
    assert preview['add'] == [dict(type='playlist', name='FromBackup', items=1)]
    assert preview['remove'] == [dict(type='playlist', name='CurrentOnly')]

    playlists_config.import_backup('20260101', 'overwrite')
    test_session.expire_all()
    names = [c.name for c in test_session.query(Collection).filter_by(kind='playlist').all()]
    assert names == ['FromBackup']


@pytest.mark.asyncio
async def test_import_still_deletes_playlists_removed_from_config(
        test_session, test_directory, playlists_config):
    """A non-empty config remains authoritative: playlists absent from it are deleted."""
    _make_playlist(test_session, name='Kept')
    _make_playlist(test_session, name='Removed')

    file = playlists_config.get_file()
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(
        'version: 1\n'
        'playlists:\n'
        '  - name: Kept\n'
        '    items:\n'
        '      - url: /map?lat=1&lon=2&z=3\n'
    )

    playlists_config.import_config()

    test_session.expire_all()
    names = [c.name for c in test_session.query(Collection).filter_by(kind='playlist').all()]
    assert names == ['Kept']


@pytest.mark.asyncio
async def test_custom_directory_round_trips(test_session, test_directory, playlists_config):
    """A playlist's custom directory survives a dump -> wipe -> import cycle."""
    custom = test_directory / 'survival' / 'fire'
    collection = _make_playlist(test_session, name='Custom Dir')
    collection.directory = custom
    test_session.commit()

    playlists_config.dump_config()

    # The config stores the directory relative to the media directory.
    data = playlists_config.read_config_file()
    entry = next(p for p in data['playlists'] if p['name'] == 'Custom Dir')
    assert entry['directory'] == 'survival/fire'

    # Wipe and re-import; the directory is restored.
    test_session.query(Collection).filter_by(kind='playlist').delete()
    test_session.commit()
    playlists_config.import_config()

    test_session.expire_all()
    collection = test_session.query(Collection).filter_by(name='Custom Dir').one()
    assert str(collection.directory) == str(custom)
