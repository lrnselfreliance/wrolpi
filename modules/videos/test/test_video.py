from modules.videos.models import Video
from wrolpi.dates import now


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
