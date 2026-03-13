import json

import pytest

from modules.videos.models import Video
from wrolpi.common import get_media_directory, get_relative_to_media_directory
from wrolpi.files.models import FileGroup


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


def test_replace_info_json_compact(test_session, make_files_structure):
    """FileGroup.replace_info_json can write compact JSON."""
    make_files_structure({'video.mp4': 'fake video'})
    fg = FileGroup.from_paths(test_session, get_media_directory() / 'video.mp4')
    test_session.add(fg)
    test_session.flush()

    info = {'title': 'Test', 'id': '123'}
    fg.replace_info_json(info, format_=False)

    json_path = get_media_directory() / 'video.info.json'
    content = json_path.read_text()
    assert '\n' not in content
    assert json.loads(content) == info


def test_replace_info_json_multiple_json_files(test_session, make_files_structure):
    """FileGroup.replace_info_json raises ValueError when multiple ambiguous .info.json files are tracked."""
    make_files_structure({
        'video.mp4': 'fake video',
        'video.a.info.json': '{"title": "one"}',
        'video.b.info.json': '{"title": "two"}',
    })
    fg = FileGroup.from_paths(test_session, get_media_directory() / 'video.mp4')
    test_session.add(fg)
    test_session.flush()

    fg.append_files(get_media_directory() / 'video.a.info.json', get_media_directory() / 'video.b.info.json')

    # Both have dots in their stems, so neither is "clean" — still raises ValueError.
    with pytest.raises(ValueError, match='multiple .info.json files'):
        fg.replace_info_json({'title': 'new'})


def test_find_unique_json_cleans_double_extension(test_session, make_files_structure):
    """When both stem.info.json and stem.mp4.info.json exist, the clean one is preferred and duplicates are ignored."""
    make_files_structure({
        'video.mp4': 'fake video',
        'video.info.json': '{"title": "clean"}',
        'video.mp4.info.json': '{"title": "double"}',
    })
    fg = FileGroup.from_paths(test_session, get_media_directory() / 'video.mp4')
    test_session.add(fg)
    test_session.flush()

    fg.append_files(get_media_directory() / 'video.info.json', get_media_directory() / 'video.mp4.info.json')

    # Should return the clean one and ignore the double-extension file.
    result = fg.info_json_path
    assert result == get_media_directory() / 'video.info.json'
    # The duplicate file still exists on disk, it's just ignored.
    assert (get_media_directory() / 'video.mp4.info.json').exists()


def test_update_wrolpi_json_merges(test_session, make_files_structure):
    """FileGroup.update_wrolpi_json merges new keys without clobbering existing ones."""
    make_files_structure({'video.mp4': 'fake video'})
    fg = FileGroup.from_paths(test_session, get_media_directory() / 'video.mp4')
    test_session.add(fg)
    test_session.flush()

    fg.replace_info_json({'title': 'Test', 'wrolpi': {'existing_key': 'keep'}})
    fg.update_wrolpi_json({'new_key': 'new_value'})

    json_path = get_media_directory() / 'video.info.json'
    written = json.loads(json_path.read_text())
    assert written['wrolpi'] == {'existing_key': 'keep', 'new_key': 'new_value'}
