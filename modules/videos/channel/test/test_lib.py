from typing import List

import pytest
import yaml

from modules.videos import schema
from modules.videos.channel import lib
from modules.videos.errors import UnknownChannel
from modules.videos.lib import save_channels_config, import_channels_config
from modules.videos.models import Channel


@pytest.mark.parametrize('params', [
    dict(),
    dict(channel_id=None),
    dict(source_id=None),
    dict(url=None),
    dict(directory=None),
])
def test_get_bad_channel(test_session, test_directory, params):
    """A Channel cannot be found without data."""
    with pytest.raises(UnknownChannel):
        lib.get_channel(test_session, **params)


def test_get_channel(test_session, test_directory, channel_factory):
    """`get_channel` can find a Channel in multiple ways."""
    channel_id_channel = channel_factory()

    source_id_channel = channel_factory()
    source_id_channel.source_id = 'the source id'

    url_channel = channel_factory()
    url_channel.url = 'https://example.com/channel'

    directory_channel = channel_factory()
    directory_channel.directory = test_directory / 'some directory'

    test_session.commit()

    channel = lib.get_channel(test_session, channel_id=channel_id_channel.id, return_dict=False)
    assert channel == channel_id_channel

    channel = lib.get_channel(test_session, source_id='the source id', return_dict=False)
    assert channel == source_id_channel

    channel = lib.get_channel(test_session, url='https://example.com/channel', return_dict=False)
    assert channel == url_channel

    # Directory can be relative, or absolute.
    channel = lib.get_channel(test_session, directory='some directory', return_dict=False)
    assert channel == directory_channel
    channel = lib.get_channel(test_session, directory=f'{test_directory}/some directory', return_dict=False)
    assert channel == directory_channel

    # Channel is found using the priority of params, incorrect data is ignored.
    params = [
        dict(channel_id=channel_id_channel.id, directory='bad directory'),
        dict(channel_id=channel_id_channel.id, directory='some directory'),
        dict(channel_id=channel_id_channel.id, source_id='bad source id'),
        dict(channel_id=channel_id_channel.id, source_id='the source id'),
    ]
    for p in params:
        assert lib.get_channel(test_session, **p, return_dict=False) == channel_id_channel
        assert lib.get_channel(test_session, **p)


@pytest.mark.asyncio
async def test_channels_no_url(async_client, test_session, test_directory, test_channels_config):
    """Test that a Channel's URL is coerced to None if it is empty."""
    channel1_directory = test_directory / 'channel1'
    channel1_directory.mkdir()
    channel2_directory = test_directory / 'channel2'
    channel2_directory.mkdir()

    channel1 = schema.ChannelPostRequest(
        name='foo',
        directory=str(channel1_directory),
    )
    channel1.url = ''
    lib.create_channel(test_session, data=channel1)

    channel2 = schema.ChannelPostRequest(
        name='bar',
        directory=str(channel2_directory),
        url=''
    )
    lib.create_channel(test_session, data=channel2)

    channels = list(test_session.query(Channel))
    assert len(channels) == 2
    assert all(i.url is None for i in channels), [(i.name, i.url) for i in channels]

    save_channels_config.activate_switch()
    import_channels_config()


@pytest.mark.asyncio
async def test_search_channels_by_name(test_session, channel_factory, video_factory):
    """
    Channels can be searched by their name.
    """
    # Create four channels with varying associated videos.
    c1 = channel_factory(name='Foo')
    c2 = channel_factory(name='bar')
    c3 = channel_factory(name='Foo Bar')
    c4 = channel_factory(name='foobar')
    video_factory(channel_id=c1.id)
    for _ in range(2):
        video_factory(channel_id=c2.id)
    for _ in range(3):
        video_factory(channel_id=c3.id)
    for _ in range(4):
        video_factory(channel_id=c4.id)
    test_session.commit()

    async def assert_search(name: str, channel_names: List[str], order_by_video_count=False):
        channels = await lib.search_channels_by_name(test_session, name, order_by_video_count=order_by_video_count)
        for channel in channels:
            channel_name = channel_names.pop(0)
            if channel.name != channel_name:
                raise AssertionError(f'Channel does not match.  Expected: {channel_name}  Got: {channel.name}')
        if channel_names:
            raise AssertionError('More channels than expected.')

    await assert_search('foo', ['Foo', 'foobar', 'Foo Bar'])
    await assert_search('bar', ['foobar', 'Foo Bar', 'bar'], True)


@pytest.mark.asyncio
async def test_tag_channel_existing(async_client, test_session, test_directory, channel_factory, tag_factory,
                                    video_factory, test_channels_config, await_switches):
    """A Channel already in a Tag's directory can still be tagged."""
    channel_directory = test_directory / 'videos/one/Channel Name'
    channel = channel_factory(name='Channel Name', download_frequency=120, directory=channel_directory)
    video_factory(channel_id=channel.id)
    test_session.commit()
    await await_switches()
    assert str(channel.directory).startswith(f'{test_directory}/videos/one/')

    tag = await tag_factory()
    await lib.tag_channel(test_session, tag.name, channel_directory, channel.id)
    await await_switches()

    # Channel's tag is saved to the config.
    with test_channels_config.open() as fh:
        config = yaml.load(fh, Loader=yaml.Loader)
    assert config['channels'][0]['tag_name'] == tag.name


@pytest.mark.asyncio
async def test_tag_channel_without_directory_saves_config(
        test_session, test_directory, channel_factory, tag_factory, test_channels_config, await_switches,
        async_client
):
    """Tagging channel without providing directory should still save config."""
    channel_directory = test_directory / 'videos' / 'Channel Name'
    channel = channel_factory(name='Channel Name', directory=channel_directory)
    test_session.commit()
    await await_switches()

    tag = await tag_factory(name='Tech')

    # Tag without providing directory (directory=None)
    await lib.tag_channel(test_session, tag.name, None, channel.id)
    test_session.commit()
    await await_switches()

    # Channel's tag should be saved to the config even without directory
    with test_channels_config.open() as fh:
        config = yaml.load(fh, Loader=yaml.Loader)
    channel_entry = next((c for c in config.get('channels', []) if c['name'] == 'Channel Name'), None)
    assert channel_entry is not None, "Channel not found in config"
    assert channel_entry.get('tag_name') == 'Tech', "Tag name not saved in config"


@pytest.mark.asyncio
async def test_untag_channel_without_directory_saves_config(
        test_session, test_directory, channel_factory, tag_factory, test_channels_config, await_switches,
):
    """Untagging channel without providing directory should still save config."""
    channel_directory = test_directory / 'videos' / 'Channel Name'
    channel = channel_factory(name='Channel Name', directory=channel_directory)
    tag = await tag_factory(name='Tech')
    channel.set_tag(tag.name)
    test_session.commit()
    await await_switches()

    # Verify tag is set
    assert channel.tag is not None

    # Untag without providing directory (tag_name=None, directory=None)
    await lib.tag_channel(test_session, None, None, channel.id)
    test_session.commit()
    await await_switches()

    # Channel's tag should be removed in the config
    with test_channels_config.open() as fh:
        config = yaml.load(fh, Loader=yaml.Loader)
    channel_entry = next((c for c in config.get('channels', []) if c['name'] == 'Channel Name'), None)
    assert channel_entry is not None, "Channel not found in config"
    assert channel_entry.get('tag_name') is None, "Tag should be removed from config"


@pytest.mark.asyncio
async def test_tag_channel_move_background_task(
        test_session, async_client, test_directory, channel_factory, tag_factory,
        await_background_tasks, test_channels_config
):
    """Test that channel move works when executed as a background task.

    This replicates the production scenario where PYTEST=False causes
    move_channel to run via background_task() instead of direct await.

    Bug: When PYTEST=False, tag_channel passes a session to background_task(),
    but by the time the task runs, the session is invalid, causing
    DetachedInstanceError when accessing channel.collection.
    """
    from unittest import mock

    # Create channel with files
    original_dir = test_directory / 'videos' / 'test_channel'
    original_dir.mkdir(parents=True)
    channel = channel_factory(name='Test Channel', directory=original_dir)
    test_session.commit()

    # Create a test file in the channel directory
    test_file = original_dir / 'test_video.mp4'
    test_file.touch()

    new_dir = test_directory / 'videos' / 'moved_channel'
    new_dir.mkdir(parents=True, exist_ok=True)

    tag = await tag_factory(name='MovedTag')
    channel_id = channel.id

    # Call tag_channel - it will use background_task() for the move.
    # The fix ensures the background task creates its own session, so
    # this should work regardless of whether the original session is closed.
    await lib.tag_channel(test_session, tag.name, new_dir, channel_id)

    # Wait for background task to complete and expire session objects
    await await_background_tasks()

    # Verify move succeeded - refresh channel from DB
    channel = Channel.find_by_id(test_session, channel_id)
    assert channel is not None, "Channel should still exist"
    assert channel.directory == new_dir, f"Channel directory should be {new_dir}, got {channel.directory}"
    assert (new_dir / 'test_video.mp4').exists(), "File should have been moved to new directory"
    assert not test_file.exists(), "File should no longer exist in original directory"
