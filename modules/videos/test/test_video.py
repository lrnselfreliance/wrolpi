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
