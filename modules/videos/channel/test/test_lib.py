import pytest

from modules.videos.channel import lib
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
