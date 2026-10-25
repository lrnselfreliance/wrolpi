"""recently_viewed.yaml imports by diffing the viewed files against the database, and writing only the differences
(see wrolpi.config_import).  A file removed from the config has its viewing history cleared, but only within the
window the config saves: an older view just fell off the end."""
from datetime import timedelta

import pytest
import yaml

from wrolpi import dates
from wrolpi.config_version import get_config_version
from wrolpi.conftest import config_was_imported
from wrolpi.files.models import FileGroup
from wrolpi.files.progress import get_recently_viewed_config
from wrolpi.test.test_config_import import edit_config, statements, writes


@pytest.fixture
def saved_viewed(test_session, test_directory, async_client, make_files_structure):
    """`a.txt`, `b.txt` (with progress) and `c.txt`, viewed in that order, saved to the config (which records its
    version)."""
    now = dates.now()
    for name, hours in (('a.txt', 3), ('b.txt', 2), ('c.txt', 1)):
        file_group = FileGroup.from_paths(test_session, *make_files_structure([name]))
        file_group.viewed = now - timedelta(hours=hours)
        if name == 'b.txt':
            file_group.progress, file_group.position = 0.5, dict(kind='page', page=5)
    test_session.commit()
    config = get_recently_viewed_config()
    config.successful_import = True
    config.dump_config()
    config.save()
    assert get_config_version(test_session, 'recently_viewed.yaml') is not None
    return config.get_file()


def viewed(test_session) -> dict:
    test_session.expire_all()
    return {i.primary_path.name: i for i in test_session.query(FileGroup) if i.viewed}


def edit_entry(path, name, **values):
    def change(data):
        next(i for i in data['files'] if i['path'] == name).update(values)

    edit_config(path, change)


@pytest.mark.asyncio
async def test_unchanged_import_writes_nothing(test_session, saved_viewed):
    """Importing a config the database already matches opens no write transaction."""
    config = get_recently_viewed_config()
    with statements() as collected:
        config.import_config()

    assert config.successful_import is True
    assert writes(collected) == []


@pytest.mark.asyncio
async def test_import_writes_only_the_differences(test_session, saved_viewed):
    """Changed progress is applied; a removed file's history is cleared; the next import writes nothing."""
    edit_entry(saved_viewed, 'b.txt', progress=0.75, position=dict(kind='page', page=7))
    edit_config(saved_viewed, lambda data: data.update(files=[i for i in data['files'] if i['path'] != 'c.txt']))

    config = get_recently_viewed_config()
    config.import_config()

    found = viewed(test_session)
    assert set(found) == {'a.txt', 'b.txt'}
    assert (found['b.txt'].progress, found['b.txt'].position) == (0.75, dict(kind='page', page=7))
    c = test_session.query(FileGroup).filter(FileGroup.primary_path.like('%c.txt')).one()
    assert (c.viewed, c.progress, c.position) == (None, None, None)
    with statements() as collected:
        config.import_config()
    assert writes(collected) == []


@pytest.mark.asyncio
async def test_older_views_are_not_removed(test_session, test_directory, async_client, make_files_structure,
                                           monkeypatch):
    """A view older than the config's oldest entry fell off the end of the saved window; it is kept, and an unchanged
    import writes nothing."""
    monkeypatch.setattr('wrolpi.files.progress.RECENTLY_VIEWED_LIMIT', 2)
    now = dates.now()
    for name, hours in (('a.txt', 3), ('b.txt', 2), ('c.txt', 1)):
        FileGroup.from_paths(test_session, *make_files_structure([name])).viewed = now - timedelta(hours=hours)
    test_session.commit()
    config = get_recently_viewed_config()
    config.successful_import = True
    config.dump_config()
    config.save()
    assert [i['path'] for i in yaml.safe_load(config.get_file().read_text())['files']] == ['c.txt', 'b.txt']

    with statements() as collected:
        config.import_config()

    assert writes(collected) == []
    assert set(viewed(test_session)) == {'a.txt', 'b.txt', 'c.txt'}


@pytest.mark.asyncio
async def test_malformed_entry_keeps_its_history(test_session, saved_viewed):
    """A malformed entry keeps its file's history (it is not removed), and does not stop the config from being
    saved (it is not counted as skipped: recently viewed is saved after every view)."""
    edit_entry(saved_viewed, 'c.txt', viewed='not a date')

    config = get_recently_viewed_config()
    config.import_config()

    assert config.import_skipped == 0
    assert set(viewed(test_session)) == {'a.txt', 'b.txt', 'c.txt'}


@pytest.mark.asyncio
async def test_moved_viewed_file_counts(test_session, test_directory, saved_viewed, make_files_structure):
    """recently_viewed.yaml saves files by path: moving a viewed FileGroup makes the database newer than the file, so
    a restart before the save does not clear its history.  Moving a file that was never viewed does not."""
    before = get_config_version(test_session, 'recently_viewed.yaml')
    a = test_session.query(FileGroup).filter_by(primary_path=test_directory / 'a.txt').one()
    a.move(test_directory / 'moved.txt')
    test_session.commit()
    assert get_config_version(test_session, 'recently_viewed.yaml') == before + 1

    never = FileGroup.from_paths(test_session, *make_files_structure(['never.txt']))
    test_session.commit()
    never.move(test_directory / 'never-moved.txt')
    test_session.commit()
    assert get_config_version(test_session, 'recently_viewed.yaml') == before + 1


@pytest.mark.asyncio
async def test_bulk_moved_viewed_file_counts(test_session, test_directory, saved_viewed):
    """A move written with raw SQL counts too."""
    from wrolpi.files.lib import _bulk_update_file_groups_db
    before = get_config_version(test_session, 'recently_viewed.yaml')
    _bulk_update_file_groups_db(test_session, {test_directory / 'a.txt': test_directory / 'moved/a.txt'})
    test_session.commit()

    assert get_config_version(test_session, 'recently_viewed.yaml') > before


@pytest.mark.asyncio
async def test_refresh_changing_primary_file_counts(test_session, test_directory, make_files_structure, video_bytes,
                                                    refresh_files):
    """A refresh that changes a viewed FileGroup's primary file counts as a change of its path."""
    make_files_structure({'video.mp4': video_bytes, 'video.jpg': 'poster'})
    await refresh_files()
    test_session.query(FileGroup).one().viewed = dates.now()
    test_session.commit()
    config_was_imported(test_session, 'recently_viewed.yaml')
    test_session.commit()

    (test_directory / 'video.mp4').unlink()
    await refresh_files()

    test_session.expire_all()
    assert test_session.query(FileGroup).one().primary_path != test_directory / 'video.mp4'
    assert get_config_version(test_session, 'recently_viewed.yaml') > 0


@pytest.mark.asyncio
async def test_without_deletes_newer_history_outside_the_window_is_kept(test_session, test_directory, async_client,
                                                                        make_files_structure, monkeypatch):
    """Without a database version, a newer view in the database wins even when it fell out of the newest views: its
    progress is kept, or (a plain view) its `viewed` is kept and the config's position is taken."""
    monkeypatch.setattr('wrolpi.files.progress.RECENTLY_VIEWED_LIMIT', 2)
    now = dates.now()
    file_groups = {name: FileGroup.from_paths(test_session, *make_files_structure([name]))
                   for name in ('progress.txt', 'plain.txt', 'b.txt', 'c.txt')}
    file_groups['progress.txt'].viewed, file_groups['progress.txt'].progress = now - timedelta(hours=3), 0.8
    file_groups['plain.txt'].viewed = now - timedelta(hours=3)
    file_groups['b.txt'].viewed, file_groups['c.txt'].viewed = now - timedelta(hours=2), now - timedelta(hours=1)
    test_session.commit()
    config = get_recently_viewed_config()
    config.get_file().parent.mkdir(exist_ok=True)
    config.get_file().write_text(yaml.dump(dict(version=1, files=[
        dict(path='progress.txt', viewed=(now - timedelta(days=1)).isoformat(), progress=0.1),
        dict(path='plain.txt', viewed=(now - timedelta(days=1)).isoformat(), progress=0.5,
             position=dict(kind='time', seconds=60)),
    ])))

    config.import_config()

    found = viewed(test_session)
    assert (found['progress.txt'].viewed, found['progress.txt'].progress) == (now - timedelta(hours=3), 0.8)
    assert (found['plain.txt'].viewed, found['plain.txt'].progress, found['plain.txt'].position) == \
           (now - timedelta(hours=3), 0.5, dict(kind='time', seconds=60.0))
