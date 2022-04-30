import shutil
from http import HTTPStatus
from pathlib import Path

from modules.videos.models import Video
from wrolpi.downloader import DownloadFrequency
from wrolpi.vars import PROJECT_DIR


def test_refresh_videos(test_client, test_session, test_directory, simple_channel, video_factory):
    subdir = test_directory / 'subdir'
    subdir.mkdir()

    # video1 is in a subdirectory.
    video1 = video_factory(channel_id=simple_channel.id, with_video_file=True, with_info_json=True,
                           with_poster_ext='jpg')
    test_session.commit()
    shutil.move(video1.video_path.path, subdir / video1.video_path.path.name)
    shutil.move(video1.poster_path.path, subdir / video1.poster_path.path.name)
    video1.video_path = subdir / video1.video_path.path.name
    video1.poster_path = None
    # video2 is in the test directory.
    video2 = video_factory(channel_id=simple_channel.id, with_video_file=True, with_info_json=True,
                           with_poster_ext='jpg')
    video2.poster_path = video1.poster_path = None
    test_session.commit()

    assert not video1.size, 'video1 should not have size during creation'

    # Create a video not in the DB.
    vid3 = test_directory / 'vid3.mp4'
    shutil.copy(PROJECT_DIR / 'test/big_buck_bunny_720p_1mb.mp4', vid3)

    # Orphan poster should be ignored.
    orphan_poster = Path(test_directory / 'channel name_20000104_defghijklmn_title.jpg')
    orphan_poster.touch()

    # Create a bogus video in the channel.
    bogus = Video(video_path='foo', channel_id=simple_channel.id)
    test_session.add(bogus)

    test_client.post('/api/videos/refresh')

    # Posters were found during refresh.
    assert video1.poster_path
    assert 'subdir' in str(video1.poster_path.path)
    assert video2.poster_path
    # Missing video3 was found
    video3: Video = test_session.query(Video).filter_by(id=4).one()
    assert video3.video_path.path == vid3
    assert video3.video_path != video1.video_path
    assert video3.video_path != video2.video_path
    # Bogus video was removed.
    assert not any('foo' in str(i.video_path.path) for i in test_session.query(Video).all())
    # Orphan file was not deleted.
    assert orphan_poster.is_file(), 'Orphan poster was removed!'

    assert video1.size, 'video1 size was not found'


def test_api_download_channel(test_session, test_client, simple_channel):
    """A Channel download (a catalog update) can be triggered via the API."""
    # simple_channel does not have a download record.
    request, response = test_client.post(f'/api/videos/download/{simple_channel.id}')
    assert response.status_code == HTTPStatus.BAD_REQUEST, response.json
    assert 'not have a download' in response.json['message']

    # Add a download frequency to the channel, this should also create a download.
    simple_channel.update(dict(download_frequency=DownloadFrequency.daily))
    test_session.commit()
    request, response = test_client.post(f'/api/videos/download/{simple_channel.id}')
    assert response.status_code == HTTPStatus.NO_CONTENT
