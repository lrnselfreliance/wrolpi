import json
import pathlib
import shutil
from http import HTTPStatus
from typing import List
from uuid import uuid4

import mock
import pytest
from PIL import Image

from modules.videos.downloader import VideoDownloader, ChannelDownloader
from modules.videos.lib import set_test_channels_config, set_test_downloader_config, format_videos_destination
from modules.videos.models import Channel, Video
from wrolpi.api_utils import api_app
from wrolpi.cmd import CommandResult
from wrolpi.downloader import DownloadFrequency, DownloadManager
from wrolpi.files.models import FileGroup, Directory
from wrolpi.vars import PROJECT_DIR


@pytest.fixture
def simple_channel(test_session, test_directory) -> Channel:
    """Get a Channel with the minimum properties.  This Channel has no download!"""
    channel = Channel(
        directory=test_directory,
        name='Simple Channel',
        url='https://example.com/channel1',
    )
    test_session.add(channel)
    test_session.commit()
    return channel


@pytest.fixture
def channel_factory(test_session, test_directory):
    """Create a random Channel with a directory, and Download."""
    from wrolpi.tags import Tag

    def factory(source_id: str = None, download_frequency: DownloadFrequency = None, url: str = None, name: str = None,
                directory: pathlib.Path = None, tag_name: str = None):
        name = name or str(uuid4())
        tag = Tag.find_by_name(tag_name) if tag_name else None
        channel = Channel(
            name=name,
            url=url or f'https://example.com/{name}',
            source_id=source_id,
            tag=tag,
            tag_id=tag.id if tag else None,
        )
        tag_name = tag.name if tag else None
        channel.directory = directory or format_videos_destination(name, tag_name, channel.url)
        channel.directory.mkdir(exist_ok=True, parents=True)
        test_session.add(channel)
        test_session.flush([channel])
        test_session.add(Directory(path=channel.directory, name=channel.directory.name))
        assert channel.id and channel.url
        if download_frequency:
            download = channel.get_or_create_download(channel.url, download_frequency)
            assert download.url == channel.url
            assert channel.downloads
        test_session.commit()
        return channel

    return factory


@pytest.fixture
def download_channel(test_session, test_directory, video_download_manager) -> Channel:
    """Get a test Channel that has a download frequency."""
    # Add a frequency to the test channel, then give it a download.
    channel = Channel(directory=test_directory, name='Download Channel', url='https://example.com/channel1',
                      source_id='channel1')
    test_session.add(channel)
    test_session.flush([channel, ])
    assert channel and channel.id and channel.url
    download = channel.get_or_create_download(channel.url, 60, test_session)
    assert download.url == channel.url
    download.frequency = DownloadFrequency.weekly
    test_session.commit()
    return channel


@pytest.fixture
def simple_video(test_session, test_directory, simple_channel, video_file) -> Video:
    """A Video with a video file, the channel is `simple_channel`."""
    video_path = test_directory / 'simple_video.mp4'
    video_file.rename(video_path)
    video = Video.from_paths(test_session, video_path)
    video.channel = simple_channel
    test_session.commit()
    video = Video.find_by_id(video.id, session=test_session)
    return video


@pytest.fixture
def video_factory(test_session, test_directory):
    """Creates Videos for testing."""

    def factory(channel_id: int = None, title: str = None, upload_date=None, with_video_file=None,
                with_info_json: dict = None, with_poster_ext: str = None, with_caption_file: bool = False,
                source_id: str = None, tag_names: List[str] = None) -> Video:
        title = title or str(uuid4())
        tag_names = tag_names or list()

        if with_video_file and isinstance(with_video_file, (pathlib.Path, str)):
            # Put the video exactly where specified for the test.
            path = pathlib.Path(with_video_file) if not isinstance(with_video_file, pathlib.Path) else with_video_file
        elif channel_id:
            # Put the video in its Channel's directory.
            channel = Channel.find_by_id(channel_id)
            path = (channel.directory or test_directory) / f'{title}.mp4'
            path.parent.mkdir(exist_ok=True, parents=True)
        else:
            # Put any video not in a Channel and without a specified file in the NO CHANNEL directory.
            (test_directory / 'videos/NO CHANNEL').mkdir(exist_ok=True, parents=True)
            path = test_directory / f'videos/NO CHANNEL/{title}.mp4'

        assert str(path).startswith(str(test_directory)), 'Video must be in the test directory'

        # Create a real video file for mimetype.
        shutil.copy(PROJECT_DIR / 'test/big_buck_bunny_720p_1mb.mp4', path)

        info_json_path = None
        if with_info_json:
            # Use the provided object as the json.
            with_info_json = {'duration': 5, 'epoch': 12345678} if with_info_json is True else with_info_json
            info_json_path = path.with_suffix('.info.json')
            info_json_path.write_text(json.dumps(with_info_json))

        poster_path = None
        if with_poster_ext:
            poster_path = path.with_suffix(f'.{with_poster_ext.lstrip(".")}')
            Image.new('RGB', (25, 25)).save(poster_path)

        caption_path = None
        if with_caption_file:
            caption_path = path.with_suffix('.en.vtt')
            shutil.copy(PROJECT_DIR / 'test/example1.en.vtt', caption_path)

        paths = (path, info_json_path, poster_path, caption_path)
        paths = list(filter(None, paths))

        video = Video.from_paths(test_session, *paths)
        video.channel_id = channel_id
        video.source_id = source_id or title
        video.file_group.published_datetime = upload_date
        video.validate()

        for tag_name in tag_names:
            video.add_tag(tag_name)

        return video

    return factory


@pytest.fixture
def video_download_manager(test_download_manager) -> DownloadManager:
    """Get a DownloadManager ready to download Videos and Channels."""
    channel_downloader = ChannelDownloader()
    video_downloader = VideoDownloader()

    test_download_manager.register_downloader(channel_downloader)
    test_download_manager.register_downloader(video_downloader)

    with mock.patch('modules.videos.downloader.YDL.extract_info') as mock_extract_info:  # prevent real downloads
        mock_extract_info.side_effect = Exception('You must patch modules.videos.downloader.YDL.extract_info!')
        yield test_download_manager


@pytest.fixture
def test_channels_config(test_directory):
    (test_directory / 'config').mkdir(exist_ok=True)
    config_path = test_directory / 'config/channels.yaml'
    with set_test_channels_config() as config:
        config.initialize(api_app.shared_ctx.channels_config)
        yield config_path


@pytest.fixture
def test_videos_downloader_config(test_directory):
    (test_directory / 'config').mkdir(exist_ok=True)
    config_path = test_directory / 'config/videos_downloader.yaml'
    set_test_downloader_config(True)
    yield config_path
    set_test_downloader_config(False)


@pytest.fixture
def mock_video_extract_info():
    with mock.patch('modules.videos.downloader.extract_info') as mock_extract_info:
        # Add some simple data so the function can be called.
        mock_extract_info.return_value = dict(
            entries=[],
            uploader='mock_video_extract_info',
            id='mock_video_extract_info',
        )
        yield mock_extract_info


@pytest.fixture
def mock_video_prepare_filename():
    with mock.patch('modules.videos.downloader.prepare_filename') as mock_prepare_filename:
        yield mock_prepare_filename


@pytest.fixture
def mock_video_process_runner():
    with mock.patch('modules.videos.downloader.VideoDownloader.process_runner') as mock_process_runner:
        mock_process_runner.return_value = \
            CommandResult(return_code=0, cancelled=False, stdout=b'', stderr=b'', elapsed=0)
        yield mock_process_runner


@pytest.fixture
def video_with_search_factory(test_session, test_directory, video_file_factory):
    """A factory that creates a Video record with an associated video File record."""

    def video_with_search(path: str = None, title: str = None, b_text: str = None, c_text: str = None,
                          d_text: str = None, mimetype: str = 'video/mp4'):
        video_file_group = FileGroup.from_paths(test_session, video_file_factory(path))
        video_file_group.a_text = title
        video_file_group.b_text = b_text
        video_file_group.c_text = c_text
        video_file_group.d_text = d_text
        video_file_group.mimetype = mimetype
        video_file_group.model = 'video'
        video = Video(file_group=video_file_group)
        test_session.add(video)
        return video

    return video_with_search


@pytest.fixture
def assert_video_search(async_client):
    """A fixture which performs a video search request against the API.

    If assert_* params are passed, the response is checked."""

    async def _search_videos(
            assert_total: int = None,
            assert_ids: List[int] = None,
            assert_paths: List[str] = None,
            search_str: str = None,
            tag_names: List[str] = None,
            offset: int = None,
            limit: int = None,
            order_by: str = None,
            channel_id: int = None,
    ):
        content = dict()
        if search_str is not None:
            content['search_str'] = search_str
        if tag_names is not None:
            content['tag_names'] = tag_names
        if offset is not None:
            content['offset'] = offset
        if limit is not None:
            content['limit'] = limit
        if order_by is not None:
            content['order_by'] = order_by
        if channel_id is not None:
            content['channel_id'] = channel_id

        request, response = await async_client.post('/api/videos/search', content=json.dumps(content))

        assert response.json
        assert response.status_code == HTTPStatus.OK

        if assert_ids is not None:
            assert 'file_groups' in response.json, 'No video file_groups in response'
            assert [i['id'] for i in response.json['file_groups']] == assert_ids, 'Video IDs do not match'

        if assert_paths is not None:
            assert 'file_groups' in response.json, 'No video file_groups in response'
            assert [i['primary_path'] for i in response.json['file_groups']] == assert_paths, 'Video paths do not match'

        if assert_total and not (count := response.json['totals']['file_groups']) == int(assert_total):
            raise AssertionError(f'Video count does not match: {count} != {assert_total}')

        return request, response

    return _search_videos
