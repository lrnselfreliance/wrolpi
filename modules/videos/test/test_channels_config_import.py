"""channels.yaml imports by diffing its Channels (and their Downloads) against the database, and writing only the
differences (see wrolpi.config_import).  A Channel is keyed by its directory."""
import pytest
import yaml

from modules.videos import lib
from modules.videos.lib import get_channels_config, import_channels_config
from modules.videos.models import Channel
from wrolpi.collections import Collection
from wrolpi.common import get_relative_to_media_directory
from wrolpi.config_version import get_config_version
from wrolpi.downloader import Download, DownloadFrequency
from wrolpi.test.test_config_import import edit_config, statements, writes


@pytest.fixture
async def saved_channels(test_session, test_directory, test_channels_config, test_download_manager_config,
                         channel_factory, tag_factory, await_switches):
    """Channel `one` (tagged, with a weekly Download) and `two`, saved to the config (which records its
    version)."""
    await tag_factory('news')
    channel_factory(name='one', url='https://example.com/one', tag_name='news',
                    download_frequency=DownloadFrequency.weekly)
    channel_factory(name='two', url='https://example.com/two')
    get_channels_config().dump_config()
    await await_switches()
    assert get_config_version(test_session, 'channels.yaml') is not None
    return test_channels_config


def channels(test_session) -> dict:
    test_session.expire_all()
    return {i.name: i for i in test_session.query(Channel)}


def edit_channel(path, name, **values):
    def change(data):
        next(i for i in data['channels'] if i['name'] == name).update(values)

    edit_config(path, change)


def directory_of(test_session, name) -> str:
    return str(get_relative_to_media_directory(channels(test_session)[name].directory))


@pytest.mark.asyncio
async def test_unchanged_import_writes_nothing(test_session, saved_channels):
    """Importing a config the database already matches opens no write transaction, nor does linking Downloads when
    there are none to link."""
    config = get_channels_config()
    with statements() as collected:
        import_channels_config()

    assert config.successful_import is True
    assert writes(collected) == []


@pytest.mark.asyncio
async def test_import_writes_only_the_differences(test_session, saved_channels):
    """A changed Channel is updated, a removed one is deleted (with its Collection), an added one is created; the
    next import writes nothing."""
    def change(data):
        data['channels'] = [i for i in data['channels'] if i['name'] != 'two']
        one = data['channels'][0]
        one.update(name='One', url='https://example.com/new-one', generate_posters=False)
        data['channels'].append(dict(name='three', directory='videos/three', url='https://example.com/three'))

    edit_config(saved_channels, change)
    config = get_channels_config()
    config.import_config()

    assert config.successful_import is True
    found = channels(test_session)
    assert set(found) == {'One', 'three'}
    assert (found['One'].url, found['One'].generate_posters, found['One'].tag_name) == \
           ('https://example.com/new-one', False, 'news')
    assert {i.name for i in test_session.query(Collection).filter_by(kind='channel')} == {'One', 'three'}
    with statements() as collected:
        config.import_config()
    assert writes(collected) == []


@pytest.mark.asyncio
async def test_downloads_follow_the_config(test_session, saved_channels):
    """A Download removed from a Channel is deleted; an added one is created (with the file's frequency) in the
    import's one write.  An existing Download keeps its own frequency."""
    edit_channel(saved_channels, 'one', downloads=[])
    edit_channel(saved_channels, 'two', downloads=[dict(url='https://example.com/two/feed', frequency=86400)])

    config = get_channels_config()
    config.import_config()

    test_session.expire_all()
    assert {(i.url, i.frequency, i.collection_id) for i in test_session.query(Download)} == {
        ('https://example.com/two/feed', 86400, channels(test_session)['two'].collection_id)}
    with statements() as collected:
        config.import_config()
    assert writes(collected) == []


@pytest.mark.asyncio
async def test_failed_import_creates_nothing(test_session, saved_channels, monkeypatch):
    """A new Download is created in the import's one write: a failure later in the write leaves nothing (it was
    committed on its own)."""
    edit_channel(saved_channels, 'two', downloads=[dict(url='https://example.com/two/feed', frequency=86400)])
    edit_config(saved_channels, lambda data: data.update(channels=[i for i in data['channels'] if i['name'] != 'one']))

    def fail(*args, **kwargs):
        raise RuntimeError('Write failed')

    monkeypatch.setattr(lib.ChannelsSection, 'delete', fail)
    with pytest.raises(RuntimeError):
        get_channels_config().import_config()

    test_session.expire_all()
    assert {i.url for i in test_session.query(Download)} == {'https://example.com/one'}
    assert set(channels(test_session)) == {'one', 'two'}


@pytest.mark.asyncio
async def test_moved_channel_is_the_same_channel(test_session, saved_channels):
    """A Channel whose directory changed in the config (its name did not) is moved, not deleted and re-created."""
    before = channels(test_session)['two'].id
    edit_channel(saved_channels, 'two', directory='videos/moved/two')

    get_channels_config().import_config()

    two = channels(test_session)['two']
    assert (two.id, directory_of(test_session, 'two')) == (before, 'videos/moved/two')


@pytest.mark.asyncio
async def test_invalid_entries_are_kept(test_session, saved_channels):
    """An entry without a name, or with an invalid directory, is skipped (counted), and its Channel is kept."""
    one_directory = directory_of(test_session, 'one')

    def change(data):
        next(i for i in data['channels'] if i['name'] == 'one').pop('name')
        next(i for i in data['channels'] if i.get('name') == 'two')['directory'] = '../outside'

    edit_config(saved_channels, change)
    config = get_channels_config()
    config.import_config()

    assert config.import_skipped == 2
    assert set(channels(test_session)) == {'one', 'two'}
    assert directory_of(test_session, 'one') == one_directory


@pytest.mark.asyncio
async def test_orphan_collections(test_session, test_directory, saved_channels):
    """A channel Collection without a Channel is deleted when the config does not list it; one the config lists
    gets its Channel."""
    test_session.add_all([
        Collection(name='orphan', kind='channel', directory=test_directory / 'videos/orphan'),
        Collection(name='listed', kind='channel', directory=test_directory / 'videos/listed'),
    ])
    test_session.commit()
    # Saved: the config lists only Channels.
    get_channels_config().dump_config()
    edit_config(saved_channels, lambda data: data['channels'].append(
        dict(name='listed', directory='videos/listed', url='https://example.com/listed')))

    get_channels_config().import_config()

    test_session.expire_all()
    assert {i.name for i in test_session.query(Collection).filter_by(kind='channel')} == {'one', 'two', 'listed'}
    assert channels(test_session)['listed'].url == 'https://example.com/listed'


@pytest.mark.asyncio
async def test_unknown_tag_with_a_skipped_entry_converges(test_session, saved_channels, test_tags_config,
                                                          await_switches):
    """Once tags.yaml is imported, a Channel's Tag that no longer exists is dropped; with a skipped entry (the config
    cannot be saved) the next import writes nothing."""
    from wrolpi.tags import get_tags_config
    get_tags_config().dump_config()
    get_tags_config().import_config()
    edit_channel(saved_channels, 'two', tag_name='gone')
    edit_config(saved_channels, lambda data: data['channels'].append(dict(directory='videos/nameless')))

    config = get_channels_config()
    config.import_config()
    await await_switches()
    assert channels(test_session)['two'].tag_name is None

    with statements() as collected:
        config.import_config()
    assert writes(collected) == []


@pytest.mark.asyncio
async def test_no_links_while_entries_are_skipped(test_session, saved_channels, await_switches):
    """Linking changes channels.yaml; while an entry is skipped the config cannot be saved, so Downloads are not
    linked (the next startup would save over the skipped entry)."""
    test_session.add(Download(url='https://example.com/two', downloader='video_channel', frequency=86400))
    test_session.commit()
    edit_config(saved_channels, lambda data: data['channels'].append(dict(directory='videos/nameless')))

    import_channels_config()
    await await_switches()

    test_session.expire_all()
    assert Download.get_by_url(test_session, 'https://example.com/two').collection_id is None
    assert get_config_version(test_session, 'channels.yaml') == yaml.safe_load(saved_channels.read_text())['version']


@pytest.mark.asyncio
async def test_moved_channel_downloads(test_session, saved_channels):
    """A moved Channel keeps the Downloads its new entry lists, and loses the ones it does not, in the same import;
    the next import writes nothing."""
    edit_channel(saved_channels, 'one', directory='videos/moved/one', downloads=[])
    edit_channel(saved_channels, 'two', directory='videos/moved/two',
                 downloads=[dict(url='https://example.com/two/feed', frequency=86400)])
    config = get_channels_config()
    config.import_config()

    test_session.expire_all()
    assert {i.url for i in test_session.query(Download)} == {'https://example.com/two/feed'}
    assert directory_of(test_session, 'one') == 'videos/moved/one'
    with statements() as collected:
        config.import_config()
    assert writes(collected) == []


@pytest.mark.asyncio
async def test_invalid_download_keeps_the_channel_downloads(test_session, saved_channels):
    """An unreadable Download of a Channel is counted as skipped, and the Channel's Downloads are kept."""
    edit_channel(saved_channels, 'one', downloads=[dict(uri='https://example.com/one')])

    config = get_channels_config()
    config.import_config()

    assert config.import_skipped == 1
    test_session.expire_all()
    assert {i.url for i in test_session.query(Download)} == {'https://example.com/one'}


@pytest.mark.asyncio
async def test_new_download_without_frequency_is_skipped(test_session, saved_channels):
    """A new Download without a frequency cannot be created: it is skipped (counted), and the next import writes
    nothing."""
    edit_channel(saved_channels, 'two', downloads=[dict(url='https://example.com/two/feed')])

    config = get_channels_config()
    with statements() as collected:
        config.import_config()

    assert config.import_skipped == 1
    assert writes(collected) == []


@pytest.mark.asyncio
async def test_no_source_id_fetch_while_entries_are_skipped(test_session, saved_channels, monkeypatch):
    """Fetching a Channel's source id changes channels.yaml; while an entry is skipped it is not fetched."""
    from wrolpi import flags
    scheduled = []
    monkeypatch.setattr(lib, 'background_task', lambda coro: scheduled.append(coro.close()))
    monkeypatch.setattr(flags.have_internet, 'is_set', lambda: True)
    monkeypatch.setattr(type(lib.download_manager), 'can_download', property(lambda self: True))
    edit_config(saved_channels, lambda data: data['channels'].extend([
        dict(name='three', directory='videos/three', url='https://example.com/three', download_missing_data=True),
        dict(directory='videos/nameless'),
    ]))

    get_channels_config().import_config()

    assert set(channels(test_session)) == {'one', 'two', 'three'}
    assert scheduled == []


@pytest.mark.asyncio
async def test_import_does_not_save_during_its_write(test_session, saved_channels, test_download_manager_config,
                                                     monkeypatch):
    """Deleting a Download inside the import's write neither skips its URL nor starts a config save (which would read
    the database before the import commits)."""
    from wrolpi.downloader import get_download_manager_config
    saves = []
    monkeypatch.setattr(lib.save_channels_config, 'activate_switch', lambda *a, **kw: saves.append('channels'))
    edit_channel(saved_channels, 'one', downloads=[])

    get_channels_config().import_config()

    assert saves == []
    assert 'https://example.com/one' not in (get_download_manager_config().skip_urls or [])


@pytest.mark.asyncio
async def test_saved_change_is_in_step(test_session, saved_channels, await_switches):
    """A Channel changed in WROLPi is saved with the database's version, so an edit of the saved file is imported
    (not saved over as an older file)."""
    print("before", get_config_version(test_session, "channels.yaml"), get_channels_config().version)
    two = channels(test_session)['two']
    two.generate_posters = not two.generate_posters
    test_session.commit()
    print("after commit", get_config_version(test_session, "channels.yaml"), get_channels_config().version)
    lib.save_channels_config()
    await await_switches()

    file_version = yaml.safe_load(saved_channels.read_text())['version']
    assert file_version == get_config_version(test_session, 'channels.yaml')

    edit_channel(saved_channels, 'two', url='https://example.com/edited')
    import_channels_config()
    assert channels(test_session)['two'].url == 'https://example.com/edited'


@pytest.mark.asyncio
async def test_once_download_is_not_a_channel_download(test_session, saved_channels):
    """A once-Download of a Channel's video is not one of the Channel's Downloads (channels.yaml does not save it), so
    importing the config neither deletes it nor writes anything."""
    two = channels(test_session)['two']
    download = Download(url='https://example.com/two/video', downloader='video', collection_id=two.collection_id)
    test_session.add(download)
    test_session.commit()
    get_channels_config().dump_config()

    config = get_channels_config()
    with statements() as collected:
        config.import_config()

    assert config.successful_import is True
    test_session.expire_all()
    assert test_session.query(Download).filter_by(url='https://example.com/two/video').one()
    assert writes(collected) == []
