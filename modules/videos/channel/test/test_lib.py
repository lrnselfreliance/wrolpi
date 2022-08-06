from unittest import mock

import pytest

from modules.videos import schema
from modules.videos.channel import lib
from modules.videos.lib import save_channels_config, import_channels_config
from modules.videos.models import Channel, Video
from wrolpi.errors import UnknownChannel


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


def test_channels_no_url(test_session, test_directory):
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

    save_channels_config()
    import_channels_config()


def test_refresh_videos_finds_channel(test_session, test_client, channel_factory, video_factory):
    """A Video will be assigned to a Channel by its info json first, then to its directory."""
    channel1 = channel_factory(source_id='channel1')
    channel2 = channel_factory(source_id='channel2')

    # Put the video in the wrong directory.  It should be matched to the info json channel first, then to it's directory
    channel1.source_id = 'channel source id'
    vid1 = video_factory(
        with_video_file=(channel2.directory / 'video1.mp4'),
        with_info_json={'channel_id': channel1.source_id},
    )
    test_session.commit()
    assert not vid1.channel_id

    with mock.patch('wrolpi.common.after_refresh') as mock_after_refresh:
        # Channel can be found in `video_cleanup`, prevent that with mock.
        mock_after_refresh.side_effect = []
        test_client.post('/api/files/refresh')

    # Channel in info_json was found during validation.
    assert vid1.channel_id == channel1.id

    # Refresh using cleanup, info json should be trusted.
    test_client.post('/api/files/refresh')
    assert vid1.channel_id == channel1.id

    # Remove the info json, the Video's Channel will be its directory.
    vid1.channel_id = None
    vid1.info_json_path.unlink()
    test_session.commit()
    test_client.post('/api/files/refresh')
    test_session.refresh(vid1)
    vid1 = test_session.query(Video).one()
    assert vid1.channel_id == channel2.id
