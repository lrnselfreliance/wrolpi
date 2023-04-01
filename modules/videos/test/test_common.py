import pathlib
import subprocess
import tempfile
from datetime import datetime
from typing import List
from unittest import mock

import pytest
import pytz
from PIL import Image

from modules.videos.models import Channel, Video
from wrolpi.common import get_absolute_media_path, sanitize_link
from wrolpi.dates import  now
from wrolpi.downloader import Download, DownloadFrequency
from wrolpi.vars import PROJECT_DIR
from .. import common
from ..common import convert_image, update_view_counts, get_video_duration, generate_video_poster, is_valid_poster
from ..lib import save_channels_config, get_channels_config, import_channels_config


def test_get_absolute_media_path():
    path = get_absolute_media_path('videos')
    assert str(path).endswith('videos')


def test_get_video_duration(test_directory):
    """
    Video duration can be retrieved from the video file.
    """
    video_path = PROJECT_DIR / 'test/big_buck_bunny_720p_1mb.mp4'
    assert get_video_duration(video_path) == 5

    with pytest.raises(FileNotFoundError):
        get_video_duration(PROJECT_DIR / 'test/does not exist.mp4')

    with pytest.raises(subprocess.CalledProcessError):
        empty_file = test_directory / 'empty.mp4'
        empty_file.touch()
        get_video_duration(empty_file)


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
    await update_view_counts(channel1.id)
    check_view_counts({'vid1': 10, 'vid2': None, 'vid3': None, 'vid4': None})

    # Channel 2 is updated, the other channels are left alone.  The 'bad_id' video is ignored.
    await update_view_counts(channel2.id)
    check_view_counts({'vid1': 10, 'vid2': 11, 'vid3': None, 'vid4': None})

    # All videos are updated.
    await update_view_counts(channel3.id)
    check_view_counts({'vid1': 10, 'vid2': 11, 'vid3': 13, 'vid4': 14})

    # An outdated view count will be overwritten.
    vid = test_session.query(Video).filter_by(id=1).one()
    vid.view_count = 8
    check_view_counts({'vid1': 8, 'vid2': 11, 'vid3': 13, 'vid4': 14})
    await update_view_counts(channel1.id)
    check_view_counts({'vid1': 10, 'vid2': 11, 'vid3': 13, 'vid4': 14})


def test_generate_video_poster(video_file):
    """
    A poster can be generated from a video file.
    """
    poster_path = video_file.with_suffix('.jpg')
    generate_video_poster(video_file)
    assert poster_path.is_file(), f'{poster_path} was not created!'
    assert poster_path.stat().st_size > 0


def test_import_channel_downloads(test_session, channel_factory, test_channels_config):
    """Importing the Channels' config should create any missing download records"""
    channel1 = channel_factory(source_id='foo')
    channel2 = channel_factory(source_id='bar')
    # channel2 has no url, but has a frequency.  Import should not create a download record.
    channel2.url = None
    channel2.download_frequency = DownloadFrequency.biweekly
    test_session.commit()
    assert channel1.download_frequency is None
    assert len(test_session.query(Channel).all()) == 2
    assert test_session.query(Download).all() == []

    def update_channel_config(conf, source_id, d):
        for c in conf.channels:
            if c['source_id'] == source_id:
                c.update(d)
        conf.save()

    # Config has no channels with a download_frequency.
    save_channels_config()
    import_channels_config()
    assert channel1.download_frequency is None
    assert len(test_session.query(Channel).all()) == 2
    assert test_session.query(Download).all() == []

    # Add a frequency to the Channel.
    channels_config = get_channels_config()
    update_channel_config(channels_config, 'foo', {'download_frequency': DownloadFrequency.biweekly})

    # Download record is created on import.
    import_channels_config()
    assert channel1.download_frequency is not None
    assert len(test_session.query(Channel).all()) == 2
    download: Download = test_session.query(Download).one()
    assert download.url == channel1.url
    assert download.frequency == channel1.download_frequency

    # Download frequency is adjusted when config file changes.
    update_channel_config(channels_config, 'foo', {'download_frequency': DownloadFrequency.weekly})
    import_channels_config()
    assert len(test_session.query(Channel).all()) == 2
    assert download.url == channel1.url
    assert download.frequency == channel1.download_frequency
    assert download.downloader == 'video_channel'
    assert download.next_download
    assert not download.error

    next_download = str(download.next_download)
    import_channels_config()
    download: Download = test_session.query(Download).one()
    assert next_download == str(download.next_download)


def test_check_for_video_corruption(video_file, test_directory):
    # The test video is not corrupt.
    assert common.check_for_video_corruption(video_file) is False

    # An empty file is corrupt.
    empty_file = test_directory / 'empty file.mp4'
    empty_file.touch()
    assert common.check_for_video_corruption(empty_file) is True

    # A video file must be complete.
    truncated_video = test_directory / 'truncated_video.mp4'
    with truncated_video.open('wb') as fh:
        fh.write(video_file.read_bytes()[:10000])
    assert common.check_for_video_corruption(truncated_video) is True

    # Check for specific ffprobe errors.
    with mock.patch('modules.videos.common.subprocess') as mock_subprocess:
        # `video_file` is ignored for these calls.
        mock_subprocess.run().stderr = b'Something\nInvalid NAL unit size'
        assert common.check_for_video_corruption(video_file) is True
        mock_subprocess.run().stderr = b'Something\nError splitting the input into NAL units'
        assert common.check_for_video_corruption(video_file) is True
        mock_subprocess.run().stderr = b'Some stderr is fine'
        assert common.check_for_video_corruption(video_file) is False
