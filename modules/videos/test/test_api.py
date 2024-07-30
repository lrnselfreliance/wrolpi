import json
from http import HTTPStatus
from pathlib import Path

import pytest

from modules.videos.models import Video, Channel
from modules.videos.video import lib as video_lib
from wrolpi.db import get_db_curs
from wrolpi.downloader import Download
from wrolpi.files.lib import refresh_files
from wrolpi.files.models import FileGroup


@pytest.mark.asyncio
async def test_refresh_videos_index(test_async_client, test_session, test_directory, video_factory):
    """The video modeler indexes video data into the Video's FileGroup."""
    video_factory(with_video_file=True, with_caption_file=True, with_poster_ext='jpg', with_info_json=True)
    test_session.commit()

    test_session.query(FileGroup).delete()
    test_session.commit()

    for _ in range(1):
        # Refreshing twice does not change the results.
        await refresh_files()

        assert test_session.query(FileGroup).count() == 1
        video: Video = test_session.query(Video).one()
        assert video.file_group.indexed is True, 'Video was not indexed'
        assert video.file_group.a_text and video.file_group.title, 'Video title was not indexed'
        assert video.file_group.d_text, 'Video captions were not indexed'

    # Delete caption file, the video should be indexed again.
    video: Video = test_session.query(Video).one()
    for path in video.caption_paths:
        path.unlink()

    await refresh_files()
    assert video.file_group.indexed is True, 'Video was not indexed'
    assert video.file_group.a_text and video.file_group.title, 'Video title was not indexed'
    assert not video.file_group.d_text, 'Video captions were not removed'


def test_refresh_videos(test_client, test_session, test_directory, simple_channel, video_factory, video_file_factory,
                        image_bytes_factory):
    subdir = test_directory / 'subdir'
    subdir.mkdir()

    # video1 is in a subdirectory, move its files into the subdirectory.
    video1 = video_factory(channel_id=simple_channel.id, with_video_file=subdir / 'video1.mp4',
                           with_info_json=True, with_poster_ext='jpg')
    test_session.commit()
    video1.file_group.size = video1.file_group.data = None
    video1.file_group.paths = list()
    # video2 is in the test directory.
    video2 = video_factory(channel_id=simple_channel.id, with_video_file=True, with_info_json=True,
                           with_poster_ext='jpg')
    video2.file_group.data = None
    video2.file_group.paths = []
    test_session.commit()

    assert not video1.file_group.size, 'video1 should not have size during creation'

    # Create a video not in the DB.
    vid3 = video_file_factory(test_directory / 'vid3.mp4')

    # Orphan poster should be ignored.
    orphan_poster = Path(test_directory / 'channel name_20000104_defghijklmn_title.jpg')
    orphan_poster.write_bytes(image_bytes_factory())

    # Create a bogus video in the channel.
    video_file = test_directory / 'foo.mp4'
    with get_db_curs(commit=True) as curs:
        stmt = "INSERT INTO file_group (mimetype, primary_path, indexed, files, model)" \
               " values ('video/mp4', %(primary_path)s, true, %(files)s, 'video') RETURNING id"
        params = {'primary_path': str(video_file), 'files': list()}
        curs.execute(stmt, params)
        video4_id = curs.fetchall()[0][0]
        stmt = "INSERT INTO video (file_group_id) values (%(video_id)s)"
        curs.execute(stmt, {'video_id': str(video4_id)})

    test_client.post('/api/files/refresh')

    test_session.expire_all()

    # Posters were found during refresh.
    assert video1.file_group.my_poster_files()
    assert 'subdir' in str(video1.file_group.my_poster_files()[0])
    assert video2.file_group.my_poster_files()
    # Missing video3 was found
    video3: Video = test_session.query(Video).filter_by(id=4).one()
    assert video3.video_path == vid3
    assert len(set(test_session.query(FileGroup.primary_path).filter(FileGroup.model == 'video'))) == 3, \
        'Should have 3 distinct video files'
    # Bogus video was removed.
    assert not any('foo.mp4' in str(i.video_path) for i in test_session.query(Video).all())
    # Orphan file was not deleted.
    assert orphan_poster.is_file(), 'Orphan poster was removed!'

    assert video1.file_group.size, 'video1 size was not found'

    # Remove video1's poster, video1 should be updated.
    video1_video_path = str(video1.video_path)
    video1.poster_path.unlink()
    test_client.post('/api/files/refresh')
    video1 = Video.get_by_path(video1_video_path, test_session)
    assert not video1.poster_path


def test_channels_with_videos(test_session, test_client, test_directory, channel_factory, video_factory):
    channel1 = channel_factory('channel1', name='channel1')
    channel2 = channel_factory('channel2', name='channel2')
    vid1 = video_factory(channel_id=channel1.id, with_video_file=True)
    vid2 = video_factory(channel_id=channel2.id, with_video_file=True)
    vid3 = video_factory(with_video_file=True)
    test_session.commit()

    vid1_path = vid1.video_path
    vid2_path = vid2.video_path
    vid3_path = vid3.video_path

    test_session.delete(vid1)
    test_session.delete(vid2)
    test_session.delete(vid3)
    test_session.commit()

    assert test_session.query(Video).count() == 0, 'Videos were not deleted'
    assert test_session.query(Channel).count() == 2, 'Channels were deleted!'
    assert vid1_path.is_file(), 'Video file was deleted'
    assert vid2_path.is_file(), 'Video file was deleted'
    assert vid3_path.is_file(), 'Video file was deleted'

    test_client.post('/api/files/refresh')

    assert test_session.query(Video).count() == 3, 'Did not find correct amount of video files.'
    assert {i[0] for i in test_session.query(Channel.name)} == {'channel1', 'channel2'}, 'Channels were changed.'

    vid1 = Video.get_by_path(vid1_path)
    vid2 = Video.get_by_path(vid2_path)
    vid3 = Video.get_by_path(vid3_path)

    assert vid1.channel == channel1
    assert vid2.channel == channel2
    assert vid3.channel is None


def test_api_download(test_session, test_client, test_directory):
    """A video can be downloaded."""
    content = dict(urls=['https://example.com/video1', ], downloader='video',
                   settings=dict(excluded_urls='example.com', destination='dest'))
    request, response = test_client.post('/api/download', content=json.dumps(content))
    assert response.status_code == HTTPStatus.NO_CONTENT

    download = test_session.query(Download).one()
    assert download.url == 'https://example.com/video1'
    assert download.downloader == 'video'
    assert download.settings['excluded_urls'] == ['example.com']
    assert download.settings['destination'] == str(test_directory / 'dest')
    assert not download.settings.get('tag_names')


def test_api_download_video_tags(test_session, test_client, tag_factory):
    """A user can request Tags for a video being downloaded."""
    tag1 = tag_factory()
    tag2 = tag_factory()

    content = dict(urls=['https://example.com/video1', ], downloader='video',
                   settings={'tag_names': [tag1.name, tag2.name]})
    request, response = test_client.post('/api/download', content=json.dumps(content))
    assert response.status_code == HTTPStatus.NO_CONTENT

    download = test_session.query(Download).one()
    assert download.url == 'https://example.com/video1'
    assert download.downloader == 'video'
    assert download.settings['tag_names'] == [tag1.name, tag2.name]


def test_search_videos_file(test_client, test_session, test_directory, video_with_search_factory, assert_video_search):
    """Test that videos can be searched and that their order is by their textsearch rank."""
    # These captions have repeated letters, so they will be higher in the ranking.
    videos = [
        ('1', 'b b b b e d d'),
        ('2', '2 b b b d'),
        ('3', 'b b'),
        ('4', 'b e e'),
        ('5', ''),
    ]
    for title, caption in videos:
        video_with_search_factory(title=title, d_text=caption)
    test_session.commit()

    # Repeated runs should return the same result
    for _ in range(2):
        # Only videos with a b are returned, ordered by the amount of b's
        assert_video_search(search_str='b', assert_ids=[1, 2, 3, 4])

    # Only two captions have e
    assert_video_search(search_str='e', assert_ids=[4, 1])

    # Only 2 contains 2
    assert_video_search(search_str='2', assert_ids=[2, ])

    # Only two captions have d
    assert_video_search(search_str='d', assert_ids=[1, 2])

    # 5 can be gotten by it's title
    assert_video_search(search_str='5', assert_ids=[5, ])

    # only video 1 has e and d
    assert_video_search(search_str='e d', assert_ids=[1, ])

    # video 1 and 4 have b and e, but 1 has more
    assert_video_search(search_str='b e', assert_ids=[1, 4])

    # Check totals are correct even with a limit
    assert_video_search(search_str='b', limit=2, assert_ids=[1, 2], assert_total=4)


def test_search_videos(test_session, video_factory, assert_video_search, simple_channel, tag_factory):
    """Search the Video table.  This does not need to use a join with the File table."""
    vid1: Video = video_factory(upload_date='2022-09-16', with_video_file=True, title='vid1')
    vid2: Video = video_factory(upload_date='2022-09-17', with_video_file=True, title='vid2',
                                channel_id=simple_channel.id)
    vid3: Video = video_factory(upload_date='2022-09-18', with_video_file=True, title='vid3')
    tag1, tag2 = tag_factory(), tag_factory()

    vid1.add_tag(tag1.id)

    # vid2 has two tags
    vid2.add_tag(tag1.id)
    vid2.add_tag(tag2.id)

    vid3.add_tag(tag2.id)

    test_session.commit()
    assert test_session.query(Video).count() == 3
    assert test_session.query(FileGroup).count() == 3

    assert_video_search(assert_total=3, assert_ids=[vid1.id, vid2.id, vid3.id], order_by='published_datetime')
    assert_video_search(assert_total=3, assert_ids=[vid3.id, vid2.id, vid1.id], order_by='-published_datetime')
    assert_video_search(assert_total=3, assert_ids=[vid3.id, vid2.id], order_by='-published_datetime', limit=2)
    assert_video_search(assert_total=3, assert_ids=[vid2.id, vid1.id], order_by='-published_datetime', limit=2,
                        offset=1)
    assert_video_search(assert_total=1, assert_ids=[vid2.id], order_by='-published_datetime',
                        channel_id=simple_channel.id)
    assert_video_search(assert_total=2, assert_ids=[vid1.id, vid2.id], tag_names=[tag1.name])
    assert_video_search(assert_total=2, assert_ids=[vid3.id, vid2.id], tag_names=[tag2.name])
    assert_video_search(assert_total=2, assert_ids=[vid1.id], tag_names=[tag1.name], limit=1)
    # Only vid2 has both tags.
    assert_video_search(assert_total=1, assert_ids=[vid2.id], tag_names=[tag1.name, tag2.name])

    # No results, no total is returned from the DB.
    assert_video_search(assert_total=0, assert_ids=[], tag_names=[tag1.name], offset=2)

    # Check all order_by.
    for order_by in video_lib.VIDEO_ORDERS:
        assert_video_search(order_by=order_by)
