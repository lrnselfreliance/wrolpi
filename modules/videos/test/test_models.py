import pytest

from modules.videos.models import Video
from wrolpi.common import get_relative_to_media_directory


@pytest.mark.asyncio()
async def test_ffprobe_stream_methods(simple_video):
    """ffprobe data can be used to get data about specific streams in the video file."""
    assert await simple_video.get_ffprobe_json()

    assert simple_video.get_streams_by_codec_type('video')
    assert simple_video.get_streams_by_codec_type('audio')
    assert simple_video.get_streams_by_codec_type('subtitle')

    assert simple_video.get_streams_by_codec_name('h264')
    assert simple_video.get_streams_by_codec_name('aac')
    assert simple_video.get_streams_by_codec_name('mov_text')


@pytest.mark.asyncio
async def test_channel_move(async_client, test_session, test_directory, channel_factory, video_factory):
    """A Channel can be moved to another directory, any files in the Channel's directory are moved."""
    channel = channel_factory(name='Channel Name')
    video = video_factory(title='Vid', channel_id=channel.id)
    extra_file = (channel.directory / 'extra.txt')
    extra_file.write_text('extra stuff')
    test_session.commit()
    assert video.channel_id == channel.id
    assert str(get_relative_to_media_directory(video.video_path)) == 'videos/Channel Name/Vid.mp4'

    # Destination must already exist.
    foo = test_directory / 'foo/New Channel Directory'
    foo.mkdir(parents=True)

    # Move the Channel.
    await channel.move_channel(foo, test_session)

    assert channel.directory == foo
    assert channel.directory != (test_directory / 'New Channel Directory')
    video = test_session.query(Video).one()
    assert str(get_relative_to_media_directory(video.video_path)) == 'foo/New Channel Directory/Vid.mp4'
    assert str(video.video_path).startswith(str(channel.directory))
    # Old directory is deleted.
    assert not (test_directory / 'Channel Name').exists()
    # Extra file was moved.
    assert not extra_file.is_file()
    assert (test_directory / 'foo/New Channel Directory/extra.txt').is_file()
    assert (test_directory / 'foo/New Channel Directory/extra.txt').read_text() == 'extra stuff'
