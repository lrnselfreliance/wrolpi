from datetime import datetime, timezone

import pytest

from modules.videos.models import Video
from wrolpi.errors import FileGroupIsTagged
from wrolpi.files import lib as files_lib
from wrolpi.files.models import FileGroup


def test_delete_video_no_channel(test_session, simple_video):
    """A Video can be deleted even if it does not have a channel."""
    assert simple_video.channel
    simple_video.channel_id = None
    test_session.commit()

    paths = list(simple_video.file_group.my_paths())

    assert not simple_video.channel
    simple_video.delete()

    # All files were deleted.
    for path in paths:
        assert not path.exists()

    test_session.commit()

    assert test_session.query(FileGroup).count() == 0
    assert test_session.query(Video).count() == 0


@pytest.mark.asyncio
async def test_delete_video_with_tag(async_client, test_session, video_factory, tag_factory):
    """You cannot delete a video with a tag."""
    video = video_factory(with_video_file=True, with_poster_ext='png')
    tag = await tag_factory()
    video.add_tag(tag.name)
    test_session.commit()

    with pytest.raises(FileGroupIsTagged):
        video.delete()

    # Video was not deleted.
    test_session.commit()
    assert test_session.query(Video).count() == 1
    assert test_session.query(FileGroup).count() == 1


@pytest.mark.asyncio
async def test_video_channel_refresh(async_client, test_session, test_directory, channel_factory, video_factory):
    """A Video will be associated with a Channel when it's files are in that Channel's directory."""
    # Create a video file in this channel's directory.
    channel = channel_factory()
    video1_path = channel.directory / 'video1.mp4'
    video_factory(channel_id=channel.id, with_video_file=video1_path, with_poster_ext='jpg')
    # Create another video outside the channel's directory.  It should not have a channel.
    video2_path = test_directory / 'video2.mp4'
    video_factory(with_video_file=video2_path)
    # Delete all FileGroups so the channel will be associated again.
    test_session.query(FileGroup).delete()
    test_session.commit()

    await files_lib.refresh_files()

    assert test_session.query(FileGroup).count() == 2
    assert test_session.query(Video).count() == 2

    # The video is associated with `simple_channel` because its file is in the Channel's directory.
    video1: Video = Video.get_by_path(video1_path, test_session)
    video2: Video = Video.get_by_path(video2_path, test_session)
    assert video1.channel == channel
    assert not video2.channel
    assert video1.__json__()['video']['channel']
    video_channel = video1.__json__()['video']['channel']
    assert video_channel['id'] == channel.id
    assert video_channel['name'] == channel.name


@pytest.mark.asyncio
async def test_delete_duplicate_video(async_client, test_session, channel_factory, video_factory, tag_factory):
    """If duplicate Video's exist, and everything about the files matches, delete a random one."""
    channel = channel_factory(name='Channel Name')
    video_path = channel.directory / f'{channel.name}_20000101_ABC123456_The video title.mp4'

    channel.info_json = {'entries': [{'id': 'ABC123456', 'title': 'The video title'}]}
    entry = channel.info_json['entries'][0]

    tag = await tag_factory()
    vid1 = video_factory(
        channel_id=channel.id,
        title=f'{channel.name}_20000101_ABC123456_The video title',
        upload_date=datetime(2000, 1, 1, tzinfo=timezone.utc),
        source_id='ABC123456',
        with_video_file=True,
        with_info_json=True,
        with_caption_file=True,
        tag_names=[tag.name, ]
    )
    vid2 = video_factory(
        channel_id=channel.id,
        title=f'{channel.name}_20000101_ABC123456_The video title ',  # Video was renamed, trailing space was removed.
        upload_date=datetime(2000, 1, 1, tzinfo=timezone.utc),
        source_id='ABC123456',
        with_video_file=True,
        with_info_json=True,
        with_caption_file=True,
    )
    vid1.file_group.url = vid2.file_group.url = 'https://example.com/video'

    assert test_session.query(Video).count() == 2

    test_session.commit()

    assert await Video.delete_duplicate_videos(test_session, 'https://example.com/video', entry['id'], video_path)
    test_session.commit()

    assert test_session.query(Video).count() == 1, 'Duplicate video was not deleted.'
    video = test_session.query(Video).one()
    assert video.video_path == video_path, 'Video path does not match'
    assert video.video_path.is_file()
    assert set(channel.directory.iterdir()) == set(video.file_group.my_paths())
    assert video.file_group.tag_names == [tag.name, ]

    # Running again has no effect.
    assert not await Video.delete_duplicate_videos(test_session, 'https://example.com/video', entry['id'], video_path)
    test_session.commit()

    assert test_session.query(Video).count() == 1, 'Duplicate video was not deleted.'
    video = test_session.query(Video).one()
    assert video.video_path.is_file()
    assert video.video_path == video_path, 'Video path does not match'
    assert set(channel.directory.iterdir()) == set(video.file_group.my_paths())
    assert video.file_group.tag_names == [tag.name, ]


@pytest.mark.asyncio
async def test_delete_renamed_video(async_client, test_session, channel_factory, video_factory, tag_factory):
    """If duplicate Video's exist, delete all the videos that do not have the new title."""
    channel = channel_factory(name='Channel Name')
    video_path = channel.directory / f'{channel.name}_20000101_ABC123456_Some new title.mp4'

    channel.info_json = {'entries': [{'id': 'ABC123456', 'title': 'Some new title'}]}
    entry = channel.info_json['entries'][0]

    tag = await tag_factory()
    vid1 = video_factory(
        channel_id=channel.id,
        title=f'{channel.name}_20000101_ABC123456_The video title',
        upload_date=datetime(2000, 1, 1, tzinfo=timezone.utc),
        source_id='ABC123456',
        with_video_file=True,
        with_info_json=True,
        with_caption_file=True,
        tag_names=[tag.name, ]
    )
    vid2 = video_factory(
        channel_id=channel.id,
        title=f'{channel.name}_20000101_ABC123456_The video title ',  # Video was renamed, trailing space was removed.
        upload_date=datetime(2000, 1, 1, tzinfo=timezone.utc),
        source_id='ABC123456',
        with_video_file=True,
        with_info_json=True,
        with_caption_file=True,
    )
    vid1.file_group.url = vid2.file_group.url = 'https://example.com/video'

    assert test_session.query(Video).count() == 2

    test_session.commit()

    await Video.delete_duplicate_videos(test_session, 'https://example.com/video', entry['id'], video_path)
    test_session.commit()

    assert test_session.query(Video).count() == 1, 'Duplicate video was not deleted.'
    video = test_session.query(Video).one()
    assert video.video_path == video_path, 'Video path does not match'
    assert video.video_path.is_file()
    assert set(channel.directory.iterdir()) == set(video.file_group.my_paths())
    assert video.file_group.tag_names == [tag.name, ]
