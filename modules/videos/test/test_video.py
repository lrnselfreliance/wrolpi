from modules.videos.models import Video
from wrolpi.dates import now
from wrolpi.files.models import File


def test_timezone(test_session):
    """
    A Video's dates should have a TimeZone.
    """
    video = Video(upload_date=now())
    test_session.add(video)
    test_session.commit()
    assert video.upload_date.tzinfo


def test_delete_video_no_channel(test_session, simple_video):
    """
    A Video can be deleted even if it does not have a channel.
    """
    assert simple_video.channel
    video_id = simple_video.id
    simple_video.channel_id = None
    test_session.commit()

    simple_video: Video = test_session.query(Video).filter_by(id=video_id).one()

    assert not simple_video.channel
    simple_video.delete()


def test_delete_video(test_session, simple_video, image_file):
    """When a Video record is deleted, all referenced file records should be deleted."""
    simple_video.poster_file = File(path=image_file)
    test_session.add(simple_video.poster_file)
    test_session.commit()

    assert simple_video.video_path.is_file(), 'Video file was not created.'
    assert simple_video.poster_path.is_file(), 'Video poster was not created.'
    assert test_session.query(Video).count() == 1, 'Video was not created.'
    assert test_session.query(File).count() == 2, 'Video file and poster file were not created.'

    simple_video.delete()
    test_session.commit()
    assert test_session.query(Video).count() == 0, 'Video was not deleted.'
    assert test_session.query(File).count() == 0, 'Video files were not deleted.'
