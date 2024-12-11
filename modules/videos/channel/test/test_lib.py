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
        lib.get_channel(**params)


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

    channel = lib.get_channel(channel_id=channel_id_channel.id, return_dict=False)
    assert channel == channel_id_channel

    channel = lib.get_channel(source_id='the source id', return_dict=False)
    assert channel == source_id_channel

    channel = lib.get_channel(url='https://example.com/channel', return_dict=False)
    assert channel == url_channel

    # Directory can be relative, or absolute.
    channel = lib.get_channel(directory='some directory', return_dict=False)
    assert channel == directory_channel
    channel = lib.get_channel(directory=f'{test_directory}/some directory', return_dict=False)
    assert channel == directory_channel

    # Channel is found using the priority of params, incorrect data is ignored.
    params = [
        dict(channel_id=channel_id_channel.id, directory='bad directory'),
        dict(channel_id=channel_id_channel.id, directory='some directory'),
        dict(channel_id=channel_id_channel.id, source_id='bad source id'),
        dict(channel_id=channel_id_channel.id, source_id='the source id'),
    ]
    for p in params:
        assert lib.get_channel(**p, return_dict=False) == channel_id_channel
        assert lib.get_channel(**p)


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
        channels = await lib.search_channels_by_name(name, order_by_video_count=order_by_video_count)
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
    await lib.tag_channel(tag.name, channel_directory, channel.id, test_session)
    await await_switches()

    # Channel's tag is saved to the config.
    with test_channels_config.open() as fh:
        config = yaml.load(fh, Loader=yaml.Loader)
    assert config['channels'][0]['tag_name'] == tag.name
