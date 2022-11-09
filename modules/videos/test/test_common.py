import pathlib
import subprocess
import tempfile
from datetime import datetime
from typing import List
from unittest import mock

import pytest
from PIL import Image

from modules.videos.models import Channel, Video
from wrolpi.common import get_absolute_media_path, sanitize_link
from wrolpi.dates import local_timezone, now
from wrolpi.downloader import Download, DownloadFrequency
from wrolpi.vars import PROJECT_DIR
from .. import common
from ..common import convert_image, remove_duplicate_video_paths, \
    apply_info_json, get_video_duration, generate_video_poster, is_valid_poster
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


@pytest.mark.parametrize(
    'paths,expected',
    (
            (['1.mp4', ], ['1.mp4', ]),
            (['1.mp4', '2.mp4'], ['1.mp4', '2.mp4']),
            (['1.mp4', '1.ogg'], ['1.mp4']),
            (['1.bad_ext', '1.other_ext'], ['1.bad_ext']),
    )
)
def test_remove_duplicate_video_paths(paths, expected):
    result = remove_duplicate_video_paths(map(pathlib.Path, paths))
    assert sorted(result) == sorted(map(pathlib.Path, expected))


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


def test_update_view_count(test_session, channel_factory, video_factory):
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
    apply_info_json(channel1.id)
    check_view_counts({'vid1': 10, 'vid2': None, 'vid3': None, 'vid4': None})

    # Channel 2 is updated, the other channels are left alone.  The 'bad_id' video is ignored.
    apply_info_json(channel2.id)
    check_view_counts({'vid1': 10, 'vid2': 11, 'vid3': None, 'vid4': None})

    # All videos are updated.
    apply_info_json(channel3.id)
    check_view_counts({'vid1': 10, 'vid2': 11, 'vid3': 13, 'vid4': 14})

    # An outdated view count will be overwritten.
    vid = test_session.query(Video).filter_by(id=1).one()
    vid.view_count = 8
    check_view_counts({'vid1': 8, 'vid2': 11, 'vid3': 13, 'vid4': 14})
    apply_info_json(channel1.id)
    check_view_counts({'vid1': 10, 'vid2': 11, 'vid3': 13, 'vid4': 14})


def test_generate_video_poster(video_file):
    """
    A poster can be generated from a video file.
    """
    poster_path = video_file.with_suffix('.jpg')
    generate_video_poster(video_file)
    assert poster_path.is_file(), f'{poster_path} was not created!'
    assert poster_path.stat().st_size > 0


def test_update_censored_videos(test_session, video_factory, simple_channel):
    vid1 = video_factory(channel_id=simple_channel.id)
    vid2 = video_factory(channel_id=simple_channel.id)
    vid3 = video_factory(channel_id=simple_channel.id)
    vid4 = video_factory()  # should not be censored because it has no channel.
    test_session.commit()

    def check_censored(expected):
        for video_id, censored in expected:
            video = test_session.query(Video).filter_by(id=video_id).one()
            assert video.censored == censored

    # Videos are not censored by default.
    test_session.commit()
    apply_info_json(simple_channel.id)
    check_censored([(vid1.id, False), (vid2.id, False), (vid3.id, False), (vid4.id, False)])

    # All videos are in the info_json.
    simple_channel.info_json = {
        'entries': [
            dict(id=vid1.source_id, view_count=0),
            dict(id=vid2.source_id, view_count=0),
            dict(id=vid3.source_id, view_count=0),
        ]
    }
    test_session.commit()

    apply_info_json(simple_channel.id)
    check_censored([(vid1.id, False), (vid2.id, False), (vid3.id, False), (vid4.id, False)])

    simple_channel.info_json = {
        'entries': [
            dict(id=vid1.source_id, view_count=0),  # vid2 is missing
            dict(id=vid3.source_id, view_count=0),
        ]
    }
    test_session.commit()
    apply_info_json(simple_channel.id)
    check_censored([(vid1.id, False), (vid2.id, True), (vid3.id, False), (vid4.id, False)])

    simple_channel.info_json = {
        'entries': [
            dict(id=vid1.source_id, view_count=0),  # vid2 is back, vid3 is missing.
            dict(id=vid2.source_id, view_count=0),
        ]
    }
    test_session.commit()
    apply_info_json(simple_channel.id)
    check_censored([(vid1.id, False), (vid2.id, False), (vid3.id, True), (vid4.id, False)])

    simple_channel.info_json = {
        'entries': []  # all videos gone
    }
    test_session.commit()
    apply_info_json(simple_channel.id)
    check_censored([(vid1.id, True), (vid2.id, True), (vid3.id, True), (vid4.id, False)])

    # Channels without info json preserve their last censored.
    simple_channel.info_json = None
    test_session.commit()
    apply_info_json(simple_channel.id)
    check_censored([(vid1.id, True), (vid2.id, True), (vid3.id, True), (vid4.id, False)])


def test_import_favorites(test_session, test_directory, simple_channel, video_factory, test_channels_config):
    """
    A favorited Video will be preserved through everything (channel deletion, DB wipe) and can be imported and will be
    favorited again.

    A Video's favorited status can only be cleared by calling `Video.delete`.
    """
    video_factory(channel_id=simple_channel.id)  # never favorited
    vid2 = video_factory(channel_id=None)  # has no channel
    vid3 = video_factory(channel_id=simple_channel.id)
    favorite = vid3.favorite = vid2.favorite = local_timezone(datetime(2000, 1, 1, 0, 0, 0))
    test_session.commit()
    vid2_video_path = vid2.video_path

    favorites = {
        str(simple_channel.directory.relative_to(test_directory)): {vid3.video_path.name: {'favorite': favorite}},
        'NO CHANNEL': {vid2.video_path.name: {'favorite': favorite}},
    }

    # Save config, verify that favorite is set.
    save_channels_config()
    config = get_channels_config()
    assert config.favorites == favorites

    def import_and_verify(favorited_ids: List[int]):
        with mock.patch('modules.videos.lib.get_channel_source_id', lambda i: 'foo'):
            import_channels_config()
            for video in test_session.query(Video).all():
                if video.id in favorited_ids:
                    assert video.favorite
                else:
                    assert not video.favorite

    # Clear the favorite (as if the DB was wiped), verify that the favorite is imported and set.
    vid2.favorite = None
    import_and_verify([vid2.id, vid3.id])

    # Removing the video does not delete the favorite.  If the DB is wiped, we do not want to lose our favorites!
    test_session.query(Video).filter_by(id=vid2.id).delete()
    test_session.commit()
    save_channels_config()
    config = get_channels_config()
    assert config.favorites == favorites
    import_and_verify([vid3.id])

    # Add vid2 again, it should be favorited on import.
    vid2 = Video(video_path=vid2_video_path)
    test_session.add(vid2)
    test_session.commit()
    import_and_verify([vid3.id, vid2.id])

    # Deleting the Video in the model really removes the favorite status.
    vid3.delete()
    config = get_channels_config()
    assert config.favorites == {'NO CHANNEL': {vid2.video_path.name: {'favorite': favorite}}}
    import_and_verify([vid2.id])


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


def test_import_channels_config_outdated(test_session, test_directory, channel_factory, test_channels_config,
                                         video_factory):
    """The Channels' config used to use a "link" to differentiate channels, test that old configs can be imported."""
    channel1 = channel_factory(name='Channel1', download_frequency=DownloadFrequency.weekly)
    channel2 = channel_factory(name='Channel2', download_frequency=DownloadFrequency.weekly)
    test_session.commit()

    vid1 = video_factory(title='vid1', channel_id=channel1.id)
    vid2 = video_factory(title='vid2', channel_id=channel2.id)
    vid3 = video_factory(title='vid3')
    vid4 = video_factory(title='vid4')
    test_session.commit()

    channel1_name, channel_1_directory = channel1.name, channel1.directory
    channel2_name, channel_2_directory = channel2.name, channel2.directory

    assert channel1.directory.exists() and channel1.directory.is_absolute()
    assert channel2.directory.exists() and channel2.directory.is_absolute()

    # Channel's used to have a relative directory in the DB.
    test_session.execute('UPDATE channel SET directory=:directory WHERE id=2',
                         dict(directory=str(channel_2_directory.relative_to(test_directory))),
                         )

    save_channels_config()

    # The config has a list of Channels, use the old method of a "dict" with the sanitized name as the key.
    channels_config = get_channels_config()
    channels_config.channels = {sanitize_link(i['name']): i for i in channels_config.channels}
    # Change frequency to verify that the channels are updated.
    for link, channel in channels_config.channels.items():
        channel['download_frequency'] = DownloadFrequency.biweekly
    # Change the favorites to the old "link" method as well.
    channels_config.favorites = {
        sanitize_link(channel1.name): {str(vid1.video_path): {'favorite': now()}},
        sanitize_link(channel2.name): {str(vid2.video_path): {'favorite': now()}},
        'NO CHANNEL': {str(vid3.video_path): {'favorite': now()}},
    }
    channels_config.save()

    assert not vid1.favorite and not vid2.favorite and not vid3.favorite and not vid3.favorite

    assert test_session.query(Channel).count() == 2

    with mock.patch('modules.videos.lib.get_channel_source_id') as mock_get_channel_source_id:
        mock_get_channel_source_id.return_value = 'some source id'
        import_channels_config()

    # No new channels were created.  Existing channels were updated.
    assert test_session.query(Channel).count() == 2
    channel1, channel2 = test_session.query(Channel).order_by(Channel.id)
    assert channel1.name == channel1_name and str(channel1.directory) == str(channel_1_directory)
    # Channel2's directory is now absolute.
    assert channel2.name == channel2_name and str(channel2.directory) == str(channel_2_directory)
    assert channel1.download_frequency == DownloadFrequency.biweekly
    assert channel2.download_frequency == DownloadFrequency.biweekly
    # Videos were favorited by their channel "link".
    assert vid1.favorite and vid2.favorite and vid3.favorite
    assert not vid4.favorite


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
