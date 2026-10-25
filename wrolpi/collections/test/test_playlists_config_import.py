"""playlists.yaml imports by diffing its playlists and their items against the database, and writing only the
differences (see wrolpi.config_import).  An item is keyed by what it points to, so moving it changes only its
position."""
import pytest
import yaml

from wrolpi.collections.config import get_playlists_config
from wrolpi.collections.models import Collection, CollectionItem
from wrolpi.config_version import get_config_version
from wrolpi.conftest import config_was_imported
from wrolpi.files.models import FileGroup
from wrolpi.test.test_config_import import edit_config, statements, writes

ONE = ['url:/one', 'file:a.txt', 'zim:home']


@pytest.fixture
async def saved_playlists(test_session, test_directory, async_client, make_files_structure, test_zim, tag_factory,
                          await_switches):
    """Playlist `One` (a URL, a file, and a Zim entry, tagged `one`) and `Two` (a URL), saved to the config (which
    records its version)."""
    from copy import deepcopy
    config = get_playlists_config()
    config._config = deepcopy(config.default_config)
    tag = await tag_factory('one')
    a, = make_files_structure({'a.txt': 'a'})
    a = FileGroup.from_paths(test_session, a)
    one = Collection(name='One', kind='playlist', description='The first', tag_id=tag.id)
    two = Collection(name='Two', kind='playlist')
    test_session.add_all([a, one, two])
    test_session.flush([a, one, two])
    one.add_url(test_session, '/one', title='One URL')
    one.add_file_group(a, session=test_session)
    one.add_zim_entry(test_session, test_zim.id, 'home')
    two.add_url(test_session, '/two')
    test_session.commit()

    config.dump_config()
    await await_switches()
    assert get_config_version(test_session, 'playlists.yaml') is not None
    return config.get_file()


def items(test_session, name='One') -> list:
    """`kind:reference` of each item of the playlist, in order."""
    test_session.expire_all()
    collection = test_session.query(Collection).filter_by(name=name, kind='playlist').one()
    return [f'{i.item_kind}:{i.url or i.zim_entry or i.file_group.primary_path.name}' for i in collection.items]


def item_ids(test_session, name='One') -> dict:
    test_session.expire_all()
    collection = test_session.query(Collection).filter_by(name=name, kind='playlist').one()
    return {i.id for i in collection.items}


def edit_playlist(path, name, change):
    def change_data(data):
        change(next(i for i in data['playlists'] if i['name'] == name))

    edit_config(path, change_data)


@pytest.mark.asyncio
async def test_unchanged_import_writes_nothing(test_session, saved_playlists):
    """Importing a config the database already matches opens no write transaction."""
    config = get_playlists_config()
    with statements() as collected:
        config.import_config()

    assert config.successful_import is True
    assert writes(collected) == []
    # The version, then one snapshot per section.
    assert len(collected) <= 4, collected
    assert items(test_session) == ONE


@pytest.mark.asyncio
async def test_reordered_items_keep_their_rows(test_session, saved_playlists):
    """Moving and inserting items changes only positions: every item keeps its row (and ID)."""
    before = item_ids(test_session)

    def change(playlist):
        playlist['items'].reverse()
        playlist['items'].insert(0, dict(url='/new', title='New'))

    edit_playlist(saved_playlists, 'One', change)
    config = get_playlists_config()
    with statements() as collected:
        config.import_config()

    assert config.successful_import is True
    assert items(test_session) == ['url:/new', 'zim:home', 'file:a.txt', 'url:/one']
    assert before < item_ids(test_session)
    assert not [i for i in writes(collected) if i.upper().startswith('DELETE FROM COLLECTION_ITEM')]


@pytest.mark.asyncio
async def test_removed_rows_are_deleted(test_session, saved_playlists):
    """A removed item and a removed playlist are deleted; a changed description and title are saved."""
    def change(data):
        data['playlists'] = [i for i in data['playlists'] if i['name'] != 'Two']
        one = data['playlists'][0]
        one['description'] = 'Changed'
        one['items'] = [i for i in one['items'] if 'zim' not in i]
        one['items'][0]['title'] = 'Renamed'

    edit_config(saved_playlists, change)
    config = get_playlists_config()
    config.import_config()

    assert config.successful_import is True
    assert {i.name for i in test_session.query(Collection).filter_by(kind='playlist')} == {'One'}
    assert items(test_session) == ['url:/one', 'file:a.txt']
    one = test_session.query(Collection).filter_by(name='One', kind='playlist').one()
    assert (one.description, one.items[0].title) == ('Changed', 'Renamed')


@pytest.mark.asyncio
async def test_unindexed_file_is_skipped_without_a_write(test_session, saved_playlists):
    """An item whose file is not indexed (yet) is skipped before the write, and keeps its place: the items after it
    keep their file positions.  The next import, with nothing else to do, writes nothing."""
    edit_playlist(saved_playlists, 'Two', lambda playlist: playlist['items'].insert(0, dict(file='later.txt')))
    config = get_playlists_config()
    config.import_config()
    test_session.expire_all()
    assert [i.position for i in test_session.query(Collection).filter_by(name='Two').one().items] == [2]

    with statements() as collected:
        config.import_config()

    assert config.successful_import is True
    assert config.import_skipped == 1
    assert writes(collected) == []
    assert items(test_session, 'Two') == ['url:/two']


@pytest.mark.asyncio
async def test_new_playlist_is_created_with_its_items(test_session, saved_playlists):
    edit_config(saved_playlists, lambda data: data['playlists'].append(dict(
        name='Three', description='New', tag_name='one', items=[dict(url='/three'), dict(file='a.txt')])))

    get_playlists_config().import_config()

    three = test_session.query(Collection).filter_by(name='Three', kind='playlist').one()
    assert (three.description, three.tag_name) == ('New', 'one')
    assert items(test_session, 'Three') == ['url:/three', 'file:a.txt']


@pytest.mark.asyncio
async def test_unknown_tag_is_dropped(test_session, saved_playlists, test_tags_config, await_switches):
    """Once tags.yaml is imported, a playlist's Tag that no longer exists is dropped and the config is saved without
    it: the next import writes nothing."""
    from wrolpi.tags import get_tags_config
    get_tags_config().dump_config()
    get_tags_config().import_config()
    edit_playlist(saved_playlists, 'One', lambda playlist: playlist.update(tag_name='gone'))

    config = get_playlists_config()
    config.import_config()
    await await_switches()

    assert test_session.query(Collection).filter_by(name='One', kind='playlist').one().tag_id is None
    assert 'gone' not in saved_playlists.read_text()
    with statements() as collected:
        config.import_config()
    assert writes(collected) == []


@pytest.mark.asyncio
async def test_moved_playlist_file_counts(test_session, test_directory, saved_playlists, make_files_structure):
    """playlists.yaml saves file items by path: moving a FileGroup in a playlist makes the database newer than the
    file, so a restart before the save does not drop the item.  Moving another FileGroup does not."""
    before = get_config_version(test_session, 'playlists.yaml')
    a = test_session.query(FileGroup).filter_by(primary_path=test_directory / 'a.txt').one()
    a.move(test_directory / 'moved.txt')
    test_session.commit()
    assert get_config_version(test_session, 'playlists.yaml') == before + 1

    other = FileGroup.from_paths(test_session, *make_files_structure({'other.txt': 'other'}))
    test_session.commit()
    other.move(test_directory / 'other-moved.txt')
    test_session.commit()
    assert get_config_version(test_session, 'playlists.yaml') == before + 1


@pytest.mark.asyncio
async def test_bulk_moved_playlist_file_counts(test_session, test_directory, saved_playlists):
    """A move written with raw SQL counts too."""
    from wrolpi.files.lib import _bulk_update_file_groups_db
    before = get_config_version(test_session, 'playlists.yaml')
    _bulk_update_file_groups_db(test_session, {test_directory / 'a.txt': test_directory / 'moved/a.txt'})
    test_session.commit()

    assert get_config_version(test_session, 'playlists.yaml') > before


@pytest.mark.asyncio
async def test_refresh_changing_primary_file_counts(test_session, test_directory, make_files_structure, video_bytes,
                                                    refresh_files):
    """A refresh that changes a playlist FileGroup's primary file counts as a change of the item's path."""
    make_files_structure({'video.mp4': video_bytes, 'video.jpg': 'poster'})
    await refresh_files()
    playlist = Collection(name='Videos', kind='playlist')
    test_session.add(playlist)
    test_session.flush([playlist])
    playlist.add_file_group(test_session.query(FileGroup).one(), session=test_session)
    test_session.commit()
    config_was_imported(test_session, 'playlists.yaml')
    test_session.commit()

    (test_directory / 'video.mp4').unlink()
    await refresh_files()

    test_session.expire_all()
    assert test_session.query(FileGroup).one().primary_path != test_directory / 'video.mp4'
    assert get_config_version(test_session, 'playlists.yaml') > 0
