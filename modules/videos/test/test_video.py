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


def test_delete_video(test_session, video_factory):
    """When a Video record is deleted, all referenced file records should be deleted."""
    video = video_factory(with_video_file=True, with_poster_ext='png')
    test_session.commit()

    assert video.video_path.is_file(), 'Video file was not created.'
    assert video.poster_path.is_file(), 'Video poster was not created.'
    assert test_session.query(Video).count() == 1, 'Video was not created.'
    assert test_session.query(FileGroup).count() == 1, 'Video file and poster file were not created.'

    video.delete()
    test_session.commit()
    assert test_session.query(Video).count() == 0, 'Video was not deleted.'
    assert test_session.query(FileGroup).count() == 0, 'Video files were not deleted.'


def test_delete_video_with_tag(test_session, video_factory, tag_factory):
    """You cannot delete a video with a tag."""
    video = video_factory(with_video_file=True, with_poster_ext='png')
    tag = tag_factory()
    video.add_tag(tag)
    test_session.commit()

    with pytest.raises(FileGroupIsTagged):
        video.delete()

    # Video was not deleted.
    test_session.commit()
    assert test_session.query(Video).count() == 1
    assert test_session.query(FileGroup).count() == 1


@pytest.mark.asyncio
async def test_video_channel_refresh(test_session, test_directory, channel_factory, video_factory):
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
