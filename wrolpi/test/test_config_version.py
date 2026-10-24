"""A database config's file and the database each carry a version (see wrolpi.config_version)."""
import pytest
import yaml

from wrolpi.collections.models import Collection
from wrolpi.config_version import get_config_version, set_config_version
from wrolpi.files.models import FileGroup
from wrolpi.tags import Tag, get_tags_config, import_tags_config


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


@pytest.mark.parametrize('file_version', [3, 9])
def test_current_file_imports_with_deletes(test_session, test_tags_config, file_version):
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


def test_unknown_database_version_imports_without_deletes(test_session, test_tags_config):
    """A config this code never imported (no database row) imports without deleting, then records its version."""
    test_session.add_all([Tag(name='kept', color='#000000'), Tag(name='unlisted', color='#000000')])
    test_session.commit()
    write_tags_config(test_tags_config, 7, ['kept', 'added'])

    import_tags_config()

    assert {i.name for i in test_session.query(Tag)} == {'kept', 'unlisted', 'added'}
    assert db_version(test_session) == 7


def test_import_button_imports_an_older_file(test_session, test_tags_config):
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
