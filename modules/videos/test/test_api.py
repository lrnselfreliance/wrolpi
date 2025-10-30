import json
from http import HTTPStatus
from pathlib import Path

import pytest

from modules.videos.models import Video, Channel
from modules.videos.video import lib as video_lib
from wrolpi.common import get_wrolpi_config
from wrolpi.db import get_db_curs
from wrolpi.downloader import Download
from wrolpi.files.lib import refresh_files
from wrolpi.files.models import FileGroup


@pytest.mark.asyncio
async def test_refresh_videos_index(async_client, test_session, test_directory, video_factory):
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


@pytest.mark.asyncio
async def test_refresh_videos(async_client, test_session, test_directory, simple_channel, video_factory,
                              video_file_factory, image_bytes_factory):
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

    await async_client.post('/api/files/refresh')

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
    await async_client.post('/api/files/refresh')
    video1 = Video.get_by_path(video1_video_path, test_session)
    assert not video1.poster_path


@pytest.mark.asyncio
async def test_channels_with_videos(test_session, async_client, test_directory, channel_factory, video_factory):
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

    await async_client.post('/api/files/refresh')

    assert test_session.query(Video).count() == 3, 'Did not find correct amount of video files.'
    from wrolpi.collections import Collection
    assert {i[0] for i in test_session.query(Collection.name).join(Channel).filter(Collection.kind == 'channel')} == {
        'channel1', 'channel2'}, 'Channels were changed.'

    vid1 = Video.get_by_path(vid1_path)
    vid2 = Video.get_by_path(vid2_path)
    vid3 = Video.get_by_path(vid3_path)

    assert vid1.channel == channel1
    assert vid2.channel == channel2
    assert vid3.channel is None


@pytest.mark.asyncio
async def test_api_download(test_session, async_client, test_directory):
    """A video can be downloaded."""
    content = dict(urls=['https://example.com/video1', ], downloader='video', destination='dest',
                   settings=dict(excluded_urls='example.com'))
    request, response = await async_client.post('/api/download', content=json.dumps(content))
    assert response.status_code == HTTPStatus.CREATED

    download = test_session.query(Download).one()
    assert download.url == 'https://example.com/video1'
    assert download.downloader == 'video'
    assert download.settings['excluded_urls'] == 'example.com'
    assert download.destination == test_directory / 'dest'
    assert not download.settings.get('tag_names')


@pytest.mark.asyncio
async def test_api_download_video_tags(test_session, async_client, tag_factory):
    """A user can request Tags for a video being downloaded."""
    tag1 = await tag_factory()
    tag2 = await tag_factory()

    content = dict(urls=['https://example.com/video1', ], downloader='video', tag_names=[tag1.name, tag2.name])
    request, response = await async_client.post('/api/download', content=json.dumps(content))
    assert response.status_code == HTTPStatus.CREATED

    download = test_session.query(Download).one()
    assert download.url == 'https://example.com/video1'
    assert download.downloader == 'video'
    assert download.tag_names == [tag1.name, tag2.name]


@pytest.mark.asyncio
async def test_search_videos_file(test_session, test_directory, video_with_search_factory,
                                  assert_video_search):
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
        await assert_video_search(search_str='b', assert_ids=[1, 2, 3, 4])

    # Only two captions have e
    await assert_video_search(search_str='e', assert_ids=[4, 1])

    # Only 2 contains 2
    await assert_video_search(search_str='2', assert_ids=[2, ])

    # Only two captions have d
    await assert_video_search(search_str='d', assert_ids=[1, 2])

    # 5 can be gotten by it's title
    await assert_video_search(search_str='5', assert_ids=[5, ])

    # only video 1 has e and d
    await assert_video_search(search_str='e d', assert_ids=[1, ])

    # video 1 and 4 have b and e, but 1 has more
    await assert_video_search(search_str='b e', assert_ids=[1, 4])

    # Check totals are correct even with a limit
    await assert_video_search(search_str='b', limit=2, assert_ids=[1, 2], assert_total=4)


@pytest.mark.asyncio
async def test_search_videos(test_session, video_factory, assert_video_search, simple_channel, tag_factory):
    """Search the Video table.  This does not need to use a join with the File table."""
    vid1: Video = video_factory(upload_date='2022-09-16', with_video_file=True, title='vid1')
    vid2: Video = video_factory(upload_date='2022-09-17', with_video_file=True, title='vid2',
                                channel_id=simple_channel.id)
    vid3: Video = video_factory(upload_date='2022-09-18', with_video_file=True, title='vid3')
    tag1, tag2 = await tag_factory(), await tag_factory()

    vid1.add_tag(tag1.id)

    # vid2 has two tags
    vid2.add_tag(tag1.id)
    vid2.add_tag(tag2.id)

    vid3.add_tag(tag2.id)

    test_session.commit()
    assert test_session.query(Video).count() == 3
    assert test_session.query(FileGroup).count() == 3

    await assert_video_search(assert_total=3, assert_ids=[vid1.id, vid2.id, vid3.id], order_by='published_datetime')
    await assert_video_search(assert_total=3, assert_ids=[vid3.id, vid2.id, vid1.id], order_by='-published_datetime')
    await assert_video_search(assert_total=3, assert_ids=[vid3.id, vid2.id], order_by='-published_datetime', limit=2)
    await assert_video_search(assert_total=3, assert_ids=[vid2.id, vid1.id], order_by='-published_datetime', limit=2,
                              offset=1)
    await assert_video_search(assert_total=1, assert_ids=[vid2.id], order_by='-published_datetime',
                              channel_id=simple_channel.id)
    await assert_video_search(assert_total=2, assert_ids=[vid1.id, vid2.id], tag_names=[tag1.name])
    await assert_video_search(assert_total=2, assert_ids=[vid3.id, vid2.id], tag_names=[tag2.name])
    await assert_video_search(assert_total=2, assert_ids=[vid1.id], tag_names=[tag1.name], limit=1)
    # Only vid2 has both tags.
    await assert_video_search(assert_total=1, assert_ids=[vid2.id], tag_names=[tag1.name, tag2.name])

    # No results, no total is returned from the DB.
    await assert_video_search(assert_total=0, assert_ids=[], tag_names=[tag1.name], offset=2)

    # Check all order_by.
    for order_by in video_lib.VIDEO_ORDERS:
        await assert_video_search(order_by=order_by)


@pytest.mark.asyncio
async def test_delete_video(async_client, test_session, video_factory, test_download_manager):
    """When a Video record is deleted, the FileGroup should be deleted.  The URL is added to the
    global skip list so the video is not downloaded again."""
    video = video_factory(with_video_file=True, with_poster_ext='png')
    video.file_group.url = 'https://example.com/video/1'
    files = video.file_group.my_paths()
    test_session.commit()

    request, response = await async_client.delete(f'/api/videos/video/{video.id}')
    assert response.status_code == HTTPStatus.NO_CONTENT

    assert test_session.query(Video).count() == 0, 'Video was not deleted.'
    assert test_session.query(FileGroup).count() == 0, 'Video FileGroup was not deleted.'
    assert not any(i.exists() for i in files), 'All files should have been deleted.'
    assert test_download_manager.is_skipped('https://example.com/video/1'), 'Video should not be downloaded again.'


@pytest.mark.asyncio
async def test_format_videos_description(async_client, test_session, test_directory, channel_factory, tag_factory):
    channel = channel_factory(name='Channel Name')
    tag = await tag_factory()
    test_session.commit()

    body = dict()
    request, response = await async_client.post('/api/videos/tag_info', json=body)
    assert response.status_code == HTTPStatus.OK
    assert response.json['videos_destination'] == 'videos'

    body = dict(channel_id=channel.id)
    request, response = await async_client.post('/api/videos/tag_info', json=body)
    assert response.status_code == HTTPStatus.OK
    assert response.json['videos_destination'] == 'videos/Channel Name'

    body = dict(channel_id=channel.id, tag_name=tag.name)
    request, response = await async_client.post('/api/videos/tag_info', json=body)
    assert response.status_code == HTTPStatus.OK
    assert response.json['videos_destination'] == 'videos/one/Channel Name'

    get_wrolpi_config().videos_destination = 'videos/%(channel_tag)s/%(channel_domain)s/%(channel_name)s'
    body = dict(channel_id=channel.id, tag_name=tag.name)
    request, response = await async_client.post('/api/videos/tag_info', json=body)
    assert response.status_code == HTTPStatus.OK
    assert response.json['videos_destination'] == 'videos/one/example.com/Channel Name'


@pytest.mark.asyncio
async def test_size_to_duration_sort(test_session, video_factory, assert_video_search):
    """Test the 'size_to_duration' sort option."""
    # Create videos with different size-to-duration ratios
    # All videos will have the same size (from the test file) but different durations

    # Video with 10 second duration (highest ratio)
    vid1 = video_factory(with_video_file=True, title='vid1', with_info_json={'duration': 10})

    # Video with 20 second duration (medium ratio)
    vid2 = video_factory(with_video_file=True, title='vid2', with_info_json={'duration': 20})

    # Video with 30 second duration (lowest ratio)
    vid3 = video_factory(with_video_file=True, title='vid3', with_info_json={'duration': 30})

    test_session.commit()

    # Verify that the videos have the expected size and length values
    vid1 = test_session.query(Video).filter_by(id=vid1.id).one()
    vid2 = test_session.query(Video).filter_by(id=vid2.id).one()
    vid3 = test_session.query(Video).filter_by(id=vid3.id).one()

    # All videos should have the same size
    assert vid1.file_group.size == vid2.file_group.size == vid3.file_group.size

    # But different lengths
    assert vid1.file_group.length == 10
    assert vid2.file_group.length == 20
    assert vid3.file_group.length == 30

    # Test ascending order (lowest ratio first)
    await assert_video_search(assert_total=3, assert_ids=[vid3.id, vid2.id, vid1.id], order_by='size_to_duration')

    # Test descending order (highest ratio first)
    await assert_video_search(assert_total=3, assert_ids=[vid1.id, vid2.id, vid3.id], order_by='-size_to_duration')


@pytest.mark.asyncio
async def test_video_file_format(async_client, test_session, fake_now):
    body = dict(video_file_format='%(uploader)s_%(upload_date)s_%(id)s_%(title)s.%(ext)s')
    request, response = await async_client.post('/api/videos/file_format', json=body)
    assert response.status_code == HTTPStatus.OK
    assert response.json['preview'] == 'WROLPi_20000101_Qz-FuenRylQ_The title of the video.mp4'

    body = dict(video_file_format='%(upload_date)s_%(id)s_%(title)s.%(ext)s')
    request, response = await async_client.post('/api/videos/file_format', json=body)
    assert response.status_code == HTTPStatus.OK
    assert response.json['preview'] == '20000101_Qz-FuenRylQ_The title of the video.mp4'

    body = dict(video_file_format='%(upload_date)s_%(id)s_%(title)s')
    request, response = await async_client.post('/api/videos/file_format', json=body)
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json['error'] == 'Filename must end with .%(ext)s'


@pytest.mark.asyncio
async def test_video_upload_file_tracking(test_session, async_client, video_factory, await_switches,
                                          make_multipart_form,
                                          image_bytes_factory):
    """Test that uploading info.json, poster, and caption files via /api/files/upload properly tracks them in Video and FileGroup."""
    from wrolpi.common import get_relative_to_media_directory

    # Step 1: Create a Video with just a video file (no info.json, poster, or captions)
    video = video_factory(with_video_file=True, title='file_tracking_test')
    test_session.commit()

    # Step 2: Verify Video and FileGroup are created, but optional files do not exist
    file_group = video.file_group
    assert not video.info_json_path, 'info.json should not exist yet.'
    assert not video.poster_path, 'Poster should not exist yet.'
    assert not video.caption_paths, 'Captions should not exist yet.'
    assert file_group.files is not None, 'FileGroup should have files array'
    initial_file_count = len(file_group.files)

    # Step 3: Upload info.json via /api/files/upload
    # Extract the video stem (e.g., "file_tracking_test")
    video_stem = video.video_path.stem

    # Create info.json content
    info_json_data = {
        'title': 'file_tracking_test',
        'duration': 60,
        'uploader': 'test_uploader'
    }
    info_json_bytes = json.dumps(info_json_data).encode()

    # Get relative destination directory
    destination = str(get_relative_to_media_directory(video.video_path.parent))
    filename = f'{video_stem}.info.json'

    # POST to /api/files/upload
    forms = [
        dict(name='destination', value=destination),
        dict(name='filename', value=filename),
        dict(name='chunkNumber', value='0'),
        dict(name='totalChunks', value='0'),
        dict(name='chunkSize', value=str(len(info_json_bytes))),
        dict(name='overwrite', value='false'),
        dict(name='chunk', value=info_json_bytes, filename='chunk'),
    ]
    body = make_multipart_form(forms)
    headers = {'Content-Type': 'multipart/form-data; boundary=-----------------------------sanic'}
    request, response = await async_client.post('/api/files/upload', content=body, headers=headers)
    assert response.status_code == HTTPStatus.CREATED, f'Upload failed with status {response.status_code}: {response.json}'

    await await_switches()

    # Step 4: Verify info.json is tracked
    # Refresh the session to get updated data
    test_session.expire_all()
    video = test_session.query(Video).filter_by(id=video.id).one()

    # Assert info.json properties exist
    assert video.info_json_path is not None, 'Video.info_json_path should exist'
    assert video.info_json_file is not None, 'Video.info_json_file should exist'

    # Assert FileGroup has the correct number of files
    assert len(video.file_group.files) == initial_file_count + 1, \
        f'FileGroup should have {initial_file_count + 1} files after adding info.json'
    assert video.file_group.data.get('info_json_path'), \
        'Video info.json should be in FileGroup.data'

    # Step 5: Upload poster image and verify it's added to the FileGroup
    file_count_before_poster = len(video.file_group.files)

    # Create image using factory
    image_data = image_bytes_factory()

    # Upload image with same stem as the Video (using .jpg)
    poster_filename = f'{video_stem}.jpg'
    forms = [
        dict(name='destination', value=destination),
        dict(name='filename', value=poster_filename),
        dict(name='chunkNumber', value='0'),
        dict(name='totalChunks', value='0'),
        dict(name='chunkSize', value=str(len(image_data))),
        dict(name='overwrite', value='false'),
        dict(name='chunk', value=image_data, filename='chunk'),
    ]
    body = make_multipart_form(forms)
    headers = {'Content-Type': 'multipart/form-data; boundary=-----------------------------sanic'}
    request, response = await async_client.post('/api/files/upload', content=body, headers=headers)
    assert response.status_code == HTTPStatus.CREATED, f'Poster upload failed with status {response.status_code}: {response.json}'

    await await_switches()

    # Refresh session to get updated data
    test_session.expire_all()
    video = test_session.query(Video).filter_by(id=video.id).one()

    # Assert poster properties exist
    assert video.poster_path is not None, 'Video.poster_path should exist'
    assert video.poster_file is not None, 'Video.poster_file should exist'
    assert video.file_group.data.get('poster_path') == video.poster_path, 'Video poster should be in FileGroup.data'

    # Assert poster is in FileGroup.files
    file_paths = [f['path'] for f in video.file_group.files]
    assert video.poster_path in file_paths, 'Poster should be in FileGroup.files'

    # Assert FileGroup has correct number of files
    assert len(video.file_group.files) == file_count_before_poster + 1, \
        f'FileGroup should have {file_count_before_poster + 1} files after adding poster'

    # Step 6: Upload caption file and verify it's added to the FileGroup
    file_count_before_caption = len(video.file_group.files)

    # Create caption content
    caption_content = """WEBVTT

00:00:00.000 --> 00:00:02.000
This is a test caption.

00:00:02.000 --> 00:00:04.000
Another line of captions.
"""

    # Upload caption with same stem as the Video
    caption_filename = f'{video_stem}.en.vtt'
    caption_bytes = caption_content.encode()
    forms = [
        dict(name='destination', value=destination),
        dict(name='filename', value=caption_filename),
        dict(name='chunkNumber', value='0'),
        dict(name='totalChunks', value='0'),
        dict(name='chunkSize', value=str(len(caption_bytes))),
        dict(name='overwrite', value='false'),
        dict(name='chunk', value=caption_bytes, filename='chunk'),
    ]
    body = make_multipart_form(forms)
    headers = {'Content-Type': 'multipart/form-data; boundary=-----------------------------sanic'}
    request, response = await async_client.post('/api/files/upload', content=body, headers=headers)
    assert response.status_code == HTTPStatus.CREATED, f'Caption upload failed with status {response.status_code}: {response.json}'

    await await_switches()

    # Refresh session to get updated data
    test_session.expire_all()
    video = test_session.query(Video).filter_by(id=video.id).one()

    # Assert caption properties exist
    assert video.caption_paths, 'Video.caption_paths should exist'
    assert len(video.caption_paths) == 1, 'Should have exactly one caption file'
    assert video.caption_files, 'Video.caption_files should exist'
    assert video.file_group.data.get('caption_paths'), 'Video captions should be in FileGroup.data'

    # Assert caption is in FileGroup.files
    file_paths = [f['path'] for f in video.file_group.files]
    assert video.caption_paths[0] in file_paths, 'Caption should be in FileGroup.files'

    # Assert FileGroup has correct number of files
    assert len(video.file_group.files) == file_count_before_caption + 1, \
        f'FileGroup should have {file_count_before_caption + 1} files after adding caption'
