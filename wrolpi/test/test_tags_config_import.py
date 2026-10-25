"""tags.yaml imports by diffing its Tags, tagged files, and tagged Zim entries against the database, and writing only
the differences (see wrolpi.config_import)."""
import pytest
import yaml

from modules.zim.models import TagZimEntry
from wrolpi import tags
from wrolpi.conftest import config_was_imported
from wrolpi.collections import Collection
from wrolpi.config_version import get_config_version
from wrolpi.files.models import FileGroup
from wrolpi.tags import Tag, TagFile
from wrolpi.test.test_config_import import edit_config, statements, writes


@pytest.fixture
async def saved_tags(test_session, test_directory, test_tags_config, make_files_structure, tag_factory, test_zim,
                     await_switches):
    """Tags `one` and `two` tag files, `three` tags a Zim entry; saved to the config (which records its version)."""
    one, two, three = await tag_factory('one'), await tag_factory('two'), await tag_factory('three')
    a, b = make_files_structure({'a.txt': 'a', 'b.txt': 'b'})
    a, b = FileGroup.from_paths(test_session, a), FileGroup.from_paths(test_session, b)
    test_session.flush([a, b])
    a.add_tag(test_session, one.id)
    a.add_tag(test_session, two.id)
    b.add_tag(test_session, one.id)
    test_zim.tag_entry(test_session, three.name, 'home')
    test_session.commit()

    tags.get_tags_config().dump_config()
    await await_switches()
    assert get_config_version(test_session, 'tags.yaml') is not None
    return test_tags_config


def tag_files(test_session):
    test_session.expire_all()
    return {(i.tag.name, i.file_group.primary_path.name) for i in test_session.query(TagFile)}


@pytest.mark.asyncio
async def test_unchanged_import_writes_nothing(test_session, saved_tags):
    """Importing a config the database already matches opens no write transaction."""
    config = tags.get_tags_config()
    with statements() as collected:
        config.import_config()

    assert config.successful_import is True
    assert writes(collected) == []
    # The version, then one snapshot per section.
    assert len(collected) <= 6, collected


@pytest.mark.asyncio
async def test_import_writes_only_the_differences(test_session, saved_tags):
    """A changed color is saved, a removed tagged file is untagged, an added one is tagged; the rest is untouched."""
    def change(data):
        data['tags']['one']['color'] = '#abcdef'
        data['tag_files'] = [i for i in data['tag_files'] if (i[0], i[1]) != ('two', 'a.txt')]
        data['tag_files'].append(['three', 'b.txt', None])

    edit_config(saved_tags, change)
    config = tags.get_tags_config()
    config.import_config()

    assert config.successful_import is True
    assert Tag.get_by_name(test_session, 'one').color == '#abcdef'
    assert tag_files(test_session) == {('one', 'a.txt'), ('one', 'b.txt'), ('three', 'b.txt')}
    # A tagged file without a date is not rewritten by the next import.
    with statements() as collected:
        config.import_config()
    assert writes(collected) == []


@pytest.mark.asyncio
async def test_removed_tag_is_deleted(test_session, saved_tags):
    """A Tag removed from the config is deleted with its tagged files and Zim entries; a Collection using it keeps
    its directory and loses only the Tag."""
    three = Tag.get_by_name(test_session, 'three')
    test_session.add(Collection(name='example.com', kind='domain', tag_id=Tag.get_by_name(test_session, 'one').id))
    test_session.commit()
    tags.get_tags_config().dump_config()

    def change(data):
        del data['tags']['one']
        del data['tags']['three']

    edit_config(saved_tags, change)
    config = tags.get_tags_config()
    config.import_config()

    assert config.successful_import is True
    test_session.expire_all()
    assert {i.name for i in test_session.query(Tag)} == {'two'}
    assert tag_files(test_session) == {('two', 'a.txt')}
    assert test_session.query(TagZimEntry).filter_by(tag_id=three.id).count() == 0
    collection = test_session.query(Collection).one()
    assert (collection.name, collection.tag_id) == ('example.com', None)


@pytest.mark.asyncio
async def test_unknown_tag_is_skipped(test_session, test_directory, saved_tags, make_files_structure):
    """A tagged file whose Tag the config does not list is skipped: no FileGroup is created for it, and the file is
    not "removed"."""
    make_files_structure({'c.txt': 'c'})
    edit_config(saved_tags, lambda data: data['tag_files'].append(['unknown', 'c.txt', None]))

    config = tags.get_tags_config()
    config.import_config()

    assert config.successful_import is True
    assert config.import_skipped == 1
    assert test_session.query(FileGroup).filter_by(primary_path=test_directory / 'c.txt').count() == 0
    assert tag_files(test_session) == {('one', 'a.txt'), ('two', 'a.txt'), ('one', 'b.txt')}


@pytest.mark.asyncio
async def test_empty_tags_delete_nothing(test_session, saved_tags):
    """An empty section cannot be told apart from a lost or blanked one: it deletes nothing."""
    edit_config(saved_tags, lambda data: data.update(tags={}, tag_files=[], tag_zims=[]))

    config = tags.get_tags_config()
    config.import_config()

    assert config.successful_import is True
    assert {i.name for i in test_session.query(Tag)} == {'one', 'two', 'three'}
    assert len(tag_files(test_session)) == 3
    assert test_session.query(TagZimEntry).count() == 1


@pytest.mark.asyncio
async def test_missing_file_group_is_created(test_session, test_directory, saved_tags, make_files_structure):
    """A tagged file on disk without a FileGroup (a rebuilt database) gets one, and is tagged."""
    make_files_structure({'c.txt': 'c'})
    edit_config(saved_tags, lambda data: data['tag_files'].append(['two', 'c.txt', '2000-01-01T00:00:00+00:00']))

    config = tags.get_tags_config()
    config.import_config()

    assert ('two', 'c.txt') in tag_files(test_session)
    with statements() as collected:
        config.import_config()
    assert writes(collected) == []


@pytest.mark.asyncio
async def test_missing_file_is_skipped_without_a_write(test_session, saved_tags):
    """A tagged file that is neither in the database nor on disk is skipped before the write: an import with nothing
    else to do writes nothing."""
    edit_config(saved_tags, lambda data: data['tag_files'].append(['two', 'gone.txt', None]))

    config = tags.get_tags_config()
    with statements() as collected:
        config.import_config()

    assert config.successful_import is True
    assert config.import_skipped == 1
    assert writes(collected) == []


@pytest.mark.asyncio
async def test_secondary_file_path_is_its_file_group(test_session, test_directory, saved_tags, make_files_structure,
                                                    video_bytes, await_switches):
    """A tagged file named by one of its group's other files (an old config) tags that FileGroup; it is not deleted
    as "removed" from the primary path, and the config is saved with the primary path."""
    video = FileGroup.from_paths(test_session, *make_files_structure({'video.mp4': video_bytes,
                                                                       'video.info.json': '{}'}))
    test_session.flush([video])
    video.add_tag(test_session, Tag.get_by_name(test_session, 'two').id)
    test_session.commit()
    tags.get_tags_config().dump_config()
    edit_config(saved_tags, lambda data: data.update(tag_files=[
        i if i[1] != 'video.mp4' else [i[0], 'video.info.json', i[2]] for i in data['tag_files']]))

    config = tags.get_tags_config()
    config.import_config()
    await await_switches()

    assert ('two', 'video.mp4') in tag_files(test_session)
    assert ['two', 'video.mp4'] in [i[:2] for i in yaml.safe_load(saved_tags.read_text())['tag_files']]


@pytest.mark.asyncio
async def test_moved_tagged_file_counts(test_session, test_directory, saved_tags):
    """tags.yaml saves tagged files by path: moving a tagged FileGroup makes the database newer than the file, so a
    restart before the save does not untag it.  Moving an untagged one does not."""
    before = get_config_version(test_session, 'tags.yaml')
    a = test_session.query(FileGroup).filter_by(primary_path=test_directory / 'a.txt').one()
    a.move(test_directory / 'moved.txt')
    test_session.commit()
    assert get_config_version(test_session, 'tags.yaml') == before + 1

    untagged = FileGroup.from_paths(test_session, test_directory / 'b.txt')
    untagged.untag(test_session, Tag.get_by_name(test_session, 'one').id)
    test_session.commit()
    before = get_config_version(test_session, 'tags.yaml')
    untagged.move(test_directory / 'untagged.txt')
    test_session.commit()
    assert get_config_version(test_session, 'tags.yaml') == before


@pytest.mark.asyncio
async def test_zim_entry_migrates_to_the_newest_zim(test_session, test_directory, test_tags_config, zim_factory,
                                                    tag_factory, await_switches):
    """A Zim entry tagged in a Zim file that is gone moves to the newest Zim of the same name, and the config is
    saved with that Zim: the next import writes nothing."""
    old = zim_factory('wikipedia_en_all_maxi_2020-01.zim')
    new = zim_factory('wikipedia_en_all_maxi_2020-02.zim')
    await tag_factory('one')
    old.tag_entry(test_session, 'one', 'home')
    test_session.commit()
    tags.get_tags_config().dump_config()
    await await_switches()
    old.delete()

    config = tags.get_tags_config()
    config.import_config()
    await await_switches()

    test_session.expire_all()
    assert [(i.tag.name, i.zim_id, i.zim_entry) for i in test_session.query(TagZimEntry)] == [('one', new.id, 'home')]
    assert 'wikipedia_en_all_maxi_2020-02.zim' in test_tags_config.read_text()
    with statements() as collected:
        config.import_config()
    assert writes(collected) == []


@pytest.mark.asyncio
async def test_bulk_moved_tagged_file_counts(test_session, test_directory, saved_tags):
    """A move written with raw SQL counts too."""
    from wrolpi.files.lib import _bulk_update_file_groups_db
    before = get_config_version(test_session, 'tags.yaml')
    _bulk_update_file_groups_db(test_session, {test_directory / 'a.txt': test_directory / 'moved/a.txt'})
    test_session.commit()

    assert get_config_version(test_session, 'tags.yaml') == before + 1


@pytest.mark.asyncio
async def test_refresh_changing_primary_file_counts(test_session, test_directory, test_tags_config, tag_factory,
                                                    make_files_structure, video_bytes, refresh_files):
    """A refresh that changes a tagged FileGroup's primary file (its video was deleted, its other files are left)
    counts as a change of the tagged file's path."""
    make_files_structure({'video.mp4': video_bytes, 'video.jpg': 'poster'})
    await refresh_files()
    tag = await tag_factory('one')
    file_group = test_session.query(FileGroup).one()
    file_group.add_tag(test_session, tag.id)
    test_session.commit()
    config_was_imported(test_session, 'tags.yaml')
    test_session.commit()

    (test_directory / 'video.mp4').unlink()
    await refresh_files()

    test_session.expire_all()
    assert test_session.query(FileGroup).one().primary_path != test_directory / 'video.mp4'
    assert get_config_version(test_session, 'tags.yaml') > 0
