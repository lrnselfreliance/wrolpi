import pathlib
import subprocess
import tempfile
from copy import copy
from unittest import mock

import pytest
from PIL import Image

from modules.videos.models import Channel, Video
from wrolpi.common import get_absolute_media_path, get_wrolpi_config
from wrolpi.downloader import Download, DownloadFrequency
from wrolpi.files import lib as files_lib
from wrolpi.vars import PROJECT_DIR
from .. import common
from ..common import convert_image, update_view_counts_and_censored, extract_video_duration, generate_video_poster, \
    is_valid_poster
from ..lib import save_channels_config, get_channels_config, import_channels_config, ChannelsConfig


def test_get_absolute_media_path(test_directory):
    path = get_absolute_media_path('videos')
    assert str(path) == f'{test_directory}/videos'

    # An absolute path is not changed.
    path = get_absolute_media_path(path)
    assert str(path) == f'{test_directory}/videos'


def test_extract_video_duration(test_directory, corrupted_video_file):
    """
    Video duration can be retrieved from the video file.
    """
    video_path = PROJECT_DIR / 'test/big_buck_bunny_720p_1mb.mp4'
    assert extract_video_duration(video_path) == 5

    with pytest.raises(FileNotFoundError):
        extract_video_duration(PROJECT_DIR / 'test/does not exist.mp4')

    with pytest.raises(subprocess.CalledProcessError):
        empty_file = test_directory / 'empty.mp4'
        empty_file.touch()
        extract_video_duration(empty_file)

    with pytest.raises(subprocess.CalledProcessError):
        extract_video_duration(corrupted_video_file)


def test_convert_image():
    """
    An image's format can be changed.  This tests that convert_image() converts from a WEBP format, to a JPEG format.
    """
    foo = Image.new('RGB', (25, 25), color='grey')

    with tempfile.TemporaryDirectory() as tempdir:
        tempdir = pathlib.Path(tempdir)

        # Save the new image to "foo.webp".
        existing_path = tempdir / 'foo.webp'
        foo.save(existing_path)
        assert Image.open(existing_path).format == 'WEBP'

        destination_path = tempdir / 'foo.jpg'
        assert not destination_path.is_file()

        # Convert the WEBP to a JPEG.  The WEBP image should be removed.
        convert_image(existing_path, destination_path)
        assert not existing_path.is_file()
        assert destination_path.is_file()
        assert Image.open(destination_path).format == 'JPEG'


@pytest.mark.parametrize(
    'ext,expected',
    [
        ('jpg', True),
        ('jpeg', True),
        ('png', False),
        ('webp', False),
        ('tif', False),
    ]
)
def test_is_valid_poster(ext, expected, test_directory):
    foo = Image.new('RGB', (25, 25), color='blue')
    image_path = test_directory / f'image.{ext}'
    foo.save(image_path)
    assert is_valid_poster(image_path) == expected, f'is_valid_poster({image_path}) should be {expected}'


@pytest.mark.asyncio
async def test_update_view_count(test_session, channel_factory, video_factory):
    def check_view_counts(view_counts):
        for source_id, view_count in view_counts.items():
            video = test_session.query(Video).filter_by(source_id=source_id).one()
            assert video.view_count == view_count

    channel1, channel2, channel3 = channel_factory(), channel_factory(), channel_factory()
    video_factory(channel_id=channel1.id, with_poster_ext='jpg', title='vid1')
    video_factory(channel_id=channel2.id, title='vid2')
    video_factory(channel_id=channel3.id, with_poster_ext='jpg', title='vid3')
    video_factory(channel_id=channel3.id, title='vid4')
    channel1.info_json = {'entries': [{'id': 'vid1', 'view_count': 10}]}
    channel2.info_json = {'entries': [{'id': 'vid2', 'view_count': 11}, {'id': 'bad_id', 'view_count': 12}]}
    channel3.info_json = {'entries': [{'id': 'vid3', 'view_count': 13}, {'id': 'vid4', 'view_count': 14}]}
    test_session.commit()

    # Check all videos are empty.
    check_view_counts({'vid1': None, 'vid2': None, 'vid3': None, 'vid4': None})

    # Channel 1 is updated, the other channels are left alone.
    await update_view_counts_and_censored(channel1.id)
    check_view_counts({'vid1': 10, 'vid2': None, 'vid3': None, 'vid4': None})

    # Channel 2 is updated, the other channels are left alone.  The 'bad_id' video is ignored.
    await update_view_counts_and_censored(channel2.id)
    check_view_counts({'vid1': 10, 'vid2': 11, 'vid3': None, 'vid4': None})

    # All videos are updated.
    await update_view_counts_and_censored(channel3.id)
    check_view_counts({'vid1': 10, 'vid2': 11, 'vid3': 13, 'vid4': 14})

    # An outdated view count will be overwritten.
    vid = test_session.query(Video).filter_by(id=1).one()
    vid.view_count = 8
    check_view_counts({'vid1': 8, 'vid2': 11, 'vid3': 13, 'vid4': 14})
    await update_view_counts_and_censored(channel1.id)
    check_view_counts({'vid1': 10, 'vid2': 11, 'vid3': 13, 'vid4': 14})


def test_generate_video_poster(video_file):
    """
    A poster can be generated from a video file.
    """
    poster_path = video_file.with_suffix('.jpg')
    _, duration = generate_video_poster(video_file)
    assert poster_path.is_file(), f'{poster_path} was not created!'
    assert poster_path.stat().st_size > 0
    assert duration == 5


@pytest.mark.asyncio
async def test_import_channel_downloads(await_switches, test_session, channel_factory, test_channels_config,
                                        tag_factory):
    """Importing the Channels' config should create any missing download records"""
    channel1 = channel_factory(source_id='foo', url='https://example.com/channel1')
    channel2 = channel_factory(source_id='bar', url='https://example.com/channel2')
    tag = await tag_factory()
    assert len(test_session.query(Channel).all()) == 2
    test_session.commit()

    def update_channel_config(conf: ChannelsConfig, source_id, d):
        # Creat a copy of the old config, replace the data of the provided Channel.
        old_config = conf._config.copy()
        for c in old_config['channels']:
            if c['source_id'] == source_id:
                c.update(d)
        conf.channels = old_config['channels']
        conf.save()

    # Two Channels, but neither have Downloads.
    save_channels_config()
    await await_switches()
    # Import after config is saved.
    import_channels_config()
    assert not channel1.downloads
    assert not channel2.downloads
    assert len(test_session.query(Channel).all()) == 2
    assert test_session.query(Download).count() == 0

    # Add a frequency to `channel1`.
    channels_config = get_channels_config()
    update_channel_config(channels_config, 'foo',
                          {'downloads': [
                              {'url': 'https://example.com/channel1', 'frequency': DownloadFrequency.weekly}
                          ]})
    await await_switches()

    # Download record is created on import.
    import_channels_config()
    assert channel1.downloads
    assert len(test_session.query(Channel).all()) == 2, 'Both Channels should still exist'
    assert test_session.query(Download).count() == 1, 'One Channel has a Download'
    download: Download = test_session.query(Download).one()
    assert download.url == channel1.url
    assert download.frequency
    assert download.downloader == 'video_channel'

    # Download.next_download was not deleted.
    next_download = str(download.next_download)
    import_channels_config()
    download: Download = test_session.query(Download).one()
    assert next_download == str(download.next_download)

    # Creating Download that matches Channel2's URL means they are related.  Delete it and it should be re-created.
    channel2.get_or_create_download(channel2.url, 60, test_session)
    save_channels_config()
    Download.find_by_url(channel2.url).delete(add_to_skip_list=False)
    test_session.commit()
    await await_switches()

    # Missing Download is re-created on import.
    import_channels_config()
    channel2 = Channel.get_by_id(channel2.id)
    downloads = test_session.query(Download).all()
    assert len(downloads) == 1, downloads
    assert len(channel1.downloads) == 1
    assert len(channel2.downloads) == 0
    assert downloads[0].downloader == 'video_channel'

    # Add a Download to Channel2 which does not match Channel.url.
    channel2.get_or_create_download('https://example.org', 60, session=test_session)
    channel2.get_or_create_download('https://example.com/channel2', 60, session=test_session)
    test_session.commit()
    save_channels_config()
    await await_switches()
    # Check config is written to match new URLs.
    config = get_channels_config()
    assert len(config.channels) == 2
    for channel_config in config.channels:
        if channel_config['source_id'] == channel2.source_id:
            assert channel_config['source_id'] == 'bar'
            assert len(channel_config['downloads']) == 2
            assert {i['url'] for i in channel_config['downloads']} \
                   == {'https://example.com/channel2', 'https://example.org'}
        else:
            assert channel_config['source_id'] == 'foo'

    # Get Channels with their Downloads.
    channels_backup = copy(get_channels_config().channels)
    # Reset Downloads.  Downloads should be recreated from the channels config file.
    [i.delete(add_to_skip_list=False) for i in test_session.query(Download).all()]
    # Write config with Channel Downloads now that the delete() has removed them from the config.
    get_channels_config().channels = channels_backup
    import_channels_config()
    channel1, channel2 = test_session.query(Channel).order_by(Channel.url).all()
    assert test_session.query(Download).count() == 3
    assert channel1.url == 'https://example.com/channel1'
    assert channel2.url == 'https://example.com/channel2'
    assert {i.url for i in channel1.downloads} == {'https://example.com/channel1'}
    assert {i.url for i in channel2.downloads} == {'https://example.com/channel2', 'https://example.org'}

    # A Channel with a `tag_name` is tagged.
    update_channel_config(get_channels_config(),
                          channel1.source_id,
                          {'tag_name': tag.name})
    import_channels_config()
    channel1, channel2 = test_session.query(Channel).order_by(Channel.url).all()
    assert channel1.tag == tag and channel1.tag_id == tag.id
    assert channel2.tag is None and channel2.tag_id is None


@pytest.mark.asyncio
async def test_import_channel_delete_missing_channels(await_switches, test_session, channel_factory,
                                                      test_channels_config):
    """The Channel import function deletes any Channels that are not in the config."""
    # Create a DB and config with two Channels.
    channel1 = channel_factory(source_id='foo')
    channel2 = channel_factory(source_id='bar')
    test_session.commit()
    # Write Channels to the config file.
    save_channels_config()
    test_session.delete(channel1)
    test_session.delete(channel2)
    test_session.commit()
    await await_switches()

    # Importing the config creates two Channels.
    import_channels_config()
    assert len(test_session.query(Channel).all()) == 2
    assert str(channel1.directory) in test_channels_config.read_text()
    assert str(channel2.directory) in test_channels_config.read_text()

    # Delete channel2 from the config file.
    config = get_channels_config()
    config_dict = config.dict()
    config_dict['channels'] = [i for i in config.channels if i['directory'] != str(channel2.directory)]
    config.update(config_dict)
    await await_switches()
    assert str(channel1.directory) in test_channels_config.read_text()
    assert str(channel2.directory) not in test_channels_config.read_text()

    # Importing the config deletes the Channel record.
    import_channels_config()
    assert len(test_session.query(Channel).all()) == 1
    assert str(channel1.directory) in test_channels_config.read_text()
    assert str(channel2.directory) not in test_channels_config.read_text()

    # Saving and importing does not change anything.
    save_channels_config()
    import_channels_config()
    assert str(channel1.directory) in test_channels_config.read_text()
    assert str(channel2.directory) not in test_channels_config.read_text()


@pytest.mark.asyncio
async def test_import_channel_download_comments(await_switches, test_session, channel_factory,
                                                test_channels_config):
    channel = channel_factory()
    assert channel.download_missing_data is True

    # download_missing_data is saved to the config.
    save_channels_config()
    await await_switches()
    assert 'download_missing_data: true' in test_channels_config.read_text()

    # change download_missing_data to False, channel should be updated on import.
    contents = test_channels_config.read_text()
    contents = contents.replace('download_missing_data: true', 'download_missing_data: false')
    test_channels_config.write_text(contents)
    import_channels_config()
    assert channel.download_missing_data is False


@pytest.mark.asyncio
async def test_ffprobe_json(async_client, video_file, corrupted_video_file):
    content = await common.ffprobe_json(video_file)
    assert not content['chapters']
    assert content['format']['duration'] == '5.312000'
    assert content['format']['size'] == '1056318'
    assert content['streams']
    assert content['streams'][0]['codec_name'] == 'h264'

    with pytest.raises(RuntimeError):
        await common.ffprobe_json(corrupted_video_file)


@pytest.mark.asyncio
async def test_video_ffprobe_json(async_client, test_session, video_file):
    """ffprobe data is extracted when a video is modeled."""
    with mock.patch('modules.videos.lib.extract_video_duration') as mock_extract_video_duration:
        mock_extract_video_duration.side_effect = Exception('duration should be from ffprobe json')
        await files_lib.refresh_files()

    video = test_session.query(Video).one()
    assert video.ffprobe_json
    assert video.file_group.length


def test_get_videos_directory(test_directory):
    """Default videos directory path"""
    # Directory does not yet exist.
    assert not (test_directory / 'videos').exists()

    # Directory is created when first gotten.
    assert common.get_videos_directory() == (test_directory / 'videos')
    assert (test_directory / 'videos').is_dir()


def test_get_custom_videos_directory(test_directory, test_wrolpi_config):
    """Custom directory can be used for videos directory."""
    config = get_wrolpi_config()
    config.videos_destination = 'custom/directory/videos'

    assert common.get_videos_directory() == (test_directory / 'custom/directory/videos')
    assert (test_directory / 'custom/directory/videos').is_dir()
    assert not (test_directory / 'videos').is_dir()
