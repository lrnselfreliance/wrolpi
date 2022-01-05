import json
import pathlib
import subprocess
import tempfile
from datetime import datetime
from typing import List
from unittest import mock
from unittest.mock import Mock, MagicMock

import pytest
from PIL import Image

from modules.videos.models import Channel, Video
from modules.videos.test.common import create_channel_structure
from wrolpi.common import get_absolute_media_path, get_config
from wrolpi.dates import local_timezone
from wrolpi.db import get_db_session
from wrolpi.test.common import build_test_directories, wrap_test_db, TestAPI
from wrolpi.vars import PROJECT_DIR
from ..common import get_matching_directories, convert_image, bulk_validate_posters, remove_duplicate_video_paths, \
    apply_info_json, get_video_duration, generate_video_poster, replace_extension, is_valid_poster, \
    get_bulk_video_info_json, import_videos_config
from ..lib import save_channels_config


class TestCommon(TestAPI):

    def test_matching_directories(self):
        structure = [
            'foo/qux/',
            'Bar/',
            'baz/baz'
            'barr',
            'bazz',
        ]

        with build_test_directories(structure) as temp_dir:
            temp_dir = pathlib.Path(temp_dir)

            # No directories have c
            matches = get_matching_directories(temp_dir / 'c')
            assert matches == []

            # Get all directories starting with f
            matches = get_matching_directories(temp_dir / 'f')
            assert matches == [str(temp_dir / 'foo')]

            # Get all directories starting with b, ignore case
            matches = get_matching_directories(temp_dir / 'b')
            assert matches == [str(temp_dir / 'Bar'), str(temp_dir / 'baz')]

            # baz matches, but it has no subdirectories
            matches = get_matching_directories(temp_dir / 'baz')
            assert matches == [str(temp_dir / 'baz')]

            # foo is an exact match, return subdirectories
            matches = get_matching_directories(temp_dir / 'foo')
            assert matches == [str(temp_dir / 'foo/qux')]


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


@pytest.mark.parametrize(
    '_structure,paths',
    (
            (
                    {'channel1': ['vid1.mp4']},
                    [
                        'channel1/vid1.mp4',
                    ],
            ),
            (
                    {'channel1': ['vid1.mp4'], 'channel2': ['vid1.mp4']},
                    [
                        'channel1/vid1.mp4',
                        'channel2/vid1.mp4',
                    ],
            ),
            (
                    {'channel1': ['vid1.mp4'], 'channel2': ['vid1.mp4', 'vid2.mp4', 'vid2.en.vtt']},
                    [
                        'channel1/vid1.mp4',
                        'channel2/vid1.mp4',
                        'channel2/vid2.mp4',
                        'channel2/vid2.en.vtt',
                    ],
            ),
    )
)
def test_create_db_structure(_structure, paths):
    @create_channel_structure(_structure)
    def test_func(_, tempdir):
        assert isinstance(tempdir, pathlib.Path)
        for path in paths:
            path = (tempdir / path)
            assert path.exists()
            assert path.is_file()

        with get_db_session() as session:
            for channel_name in _structure:
                channel = session.query(Channel).filter_by(name=channel_name).one()
                assert (tempdir / channel_name).is_dir()
                assert channel
                assert channel.directory == tempdir / channel_name
                assert len(channel.videos) == len([i for i in _structure[channel_name] if i.endswith('mp4')])

    with tempfile.TemporaryDirectory() as tmp_dir, \
            mock.patch('wrolpi.media_path.get_media_directory') as mock_get_directory:
        mock_get_directory.return_value = pathlib.Path(tmp_dir)
        test_ = MagicMock()
        test_.tmp_dir.name = tmp_dir
        test_func(test_)


@wrap_test_db
@create_channel_structure(
    {
        'channel1': ['vid1.mp4', 'vid1.jpg'],
        'channel2': ['vid2.flv', 'vid2.webp'],
    }
)
def test_bulk_replace_invalid_posters(tempdir: pathlib.Path):
    """
    Test that when a video has an invalid poster format, we convert it to JPEG.
    """
    channel1, channel2 = sorted(tempdir.iterdir())
    jpg, mp4 = sorted(channel1.iterdir())
    flv, webp = sorted(channel2.iterdir())

    Image.new('RGB', (25, 25)).save(jpg)
    Image.new('RGB', (25, 25)).save(webp)

    with open(jpg, 'rb') as jpg_fh, open(webp, 'rb') as webp_fh:
        # Files are different formats.
        jpg_fh_contents = jpg_fh.read()
        webp_fh_contents = webp_fh.read()
        assert jpg_fh_contents != webp_fh_contents
        assert Image.open(jpg_fh).format == 'JPEG'
        assert Image.open(webp_fh).format == 'WEBP'

    with get_db_session() as session:
        vid1 = session.query(Video).filter_by(poster_path=f'{tempdir}/channel1/vid1.jpg').one()
        assert vid1.validated_poster is False

        vid2 = session.query(Video).filter_by(poster_path=f'{tempdir}/channel2/vid2.webp').one()
        assert vid2.validated_poster is False

    # Convert the WEBP image.  convert_image() should only be called once.
    mocked_convert_image = Mock(wraps=convert_image)
    with mock.patch('modules.videos.common.convert_image', mocked_convert_image):
        video_ids = [vid1.id, vid2.id]
        bulk_validate_posters(video_ids)

    mocked_convert_image.assert_called_once_with(webp, tempdir / 'channel2/vid2.jpg')

    with get_db_session() as session:
        # Get the video by ID because it's poster is now a JPEG.
        vid2 = session.query(Video).filter_by(id=vid2.id).one()
        assert str(vid2.poster_path.path).split('/')[-1] == 'vid2.jpg'
        assert all('webp' not in str(i.poster_path.path) for i in session.query(Video).all())
        assert vid2.validated_poster is True

        # Vid1's image was validated, but not converted.
        vid1 = session.query(Video).filter_by(id=vid1.id).one()
        assert str(vid1.poster_path.path).split('/')[-1] == 'vid1.jpg'
        assert vid1.validated_poster is True

    # Old webp was removed
    assert not webp.is_file()
    new_jpg = tempdir / 'channel2/vid2.jpg'
    assert new_jpg.is_file()
    # chmod 644
    assert new_jpg.stat().st_mode == 0o100644
    with open(new_jpg, 'rb') as new_jpg_fh:
        # The converted image is the same as the other JPEG because both are black 25x25 pixel images.
        assert jpg_fh_contents == new_jpg_fh.read()
        assert Image.open(new_jpg_fh).format == 'JPEG'

    # Calling convert again has no effect.
    mocked_convert_image.reset_mock()
    with mock.patch('modules.videos.common.convert_image', mocked_convert_image):
        video_ids = [vid1.id, vid2.id]
        bulk_validate_posters(video_ids)

    mocked_convert_image.assert_not_called()


@wrap_test_db
@create_channel_structure(
    {
        'channel1': ['vid1.mp4', 'vid1.jpg'],
        'channel2': ['vid2.mp4'],
        'channel3': ['vid3.mp4', 'vid4.mp4'],
    }
)
def test_update_view_count(tempdir: pathlib.Path):
    def check_view_counts(view_counts):
        with get_db_session() as session_:
            for source_id, view_count in view_counts.items():
                vid = session_.query(Video).filter_by(source_id=source_id).one()
                assert vid.view_count == view_count

    with get_db_session(commit=True) as session:
        channel1, channel2, channel3 = session.query(Channel).order_by(Channel.id).all()
        channel1.info_json = {'entries': [{'id': 'vid1.mp4', 'view_count': 10}]}
        channel2.info_json = {'entries': [{'id': 'vid2.mp4', 'view_count': 11}, {'id': 'bad_id', 'view_count': 12}]}
        channel3.info_json = {'entries': [{'id': 'vid3.mp4', 'view_count': 13}, {'id': 'vid4.mp4', 'view_count': 14}]}

        # Use the video file name as a unique source_id
        for v in session.query(Video).all():
            v.source_id = str(v.video_path.path).split('/')[-1]

    # Check all videos are empty.
    check_view_counts({'vid1.mp4': None, 'vid2.mp4': None, 'vid3.mp4': None, 'vid4.mp4': None})

    # Channel 1 is updated, the other channels are left alone.
    apply_info_json(channel1.id)
    check_view_counts({'vid1.mp4': 10, 'vid2.mp4': None, 'vid3.mp4': None, 'vid4.mp4': None})

    # Channel 2 is updated, the other channels are left alone.  The 'bad_id' video is ignored.
    apply_info_json(channel2.id)
    check_view_counts({'vid1.mp4': 10, 'vid2.mp4': 11, 'vid3.mp4': None, 'vid4.mp4': None})

    # All videos are updated.
    apply_info_json(channel3.id)
    check_view_counts({'vid1.mp4': 10, 'vid2.mp4': 11, 'vid3.mp4': 13, 'vid4.mp4': 14})

    # An outdated view count will be overwritten.
    with get_db_session(commit=True) as session:
        vid = session.query(Video).filter_by(id=1).one()
        vid.view_count = 8
    check_view_counts({'vid1.mp4': 8, 'vid2.mp4': 11, 'vid3.mp4': 13, 'vid4.mp4': 14})
    apply_info_json(channel1.id)
    check_view_counts({'vid1.mp4': 10, 'vid2.mp4': 11, 'vid3.mp4': 13, 'vid4.mp4': 14})


def test_generate_video_poster(video_file):
    """
    A poster can be generated from a video file.
    """
    poster_path = replace_extension(video_file, '.jpg')
    assert not poster_path.is_file(), f'{poster_path} already exists!'
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


@pytest.mark.asyncio
async def test_missing_title(test_session, simple_video):
    """
    A Video title will be filled out by `get_bulk_video_info_json`.
    """
    video_path: pathlib.Path = simple_video.video_path.path
    simple_video.duration = 10  # don't update the duration during get_bulk_video_info_json()

    info_json_path = video_path.with_suffix('.info.json')
    info_json_path.write_text(json.dumps({'title': 'info json title &amp;'}))
    simple_video.info_json_path = info_json_path
    test_session.commit()

    # simple_video does not come with a title.
    assert not simple_video.title

    # Title is fetched from the info_json.
    await get_bulk_video_info_json([simple_video.id])
    assert simple_video.title == 'info json title &'

    # No info_json means the filename is used.
    simple_video.title = None
    simple_video.info_json_path = None
    test_session.commit()
    await get_bulk_video_info_json([simple_video.id])
    assert simple_video.title == 'simple_video'


def test_import_favorites(test_session, simple_channel, video_factory):
    """
    A favorited Video will be preserved through everything (channel deletion, DB wipe) and can be imported and will be
    favorited again.

    A Video's favorited status can only be cleared by calling `Video.delete`.
    """
    video_factory(channel_id=simple_channel.id)  # never favorited
    vid2 = video_factory(channel_id=None)  # has no channel
    vid3 = video_factory(channel_id=simple_channel.id)
    favorite = vid2.favorite = local_timezone(datetime(2000, 1, 1, 0, 0, 0))
    vid3.favorite = favorite
    test_session.commit()
    vid2_video_path = vid2.video_path.path

    favorites = {
        simple_channel.link: {vid3.video_path.path.name: {'favorite': favorite}},
        'NO CHANNEL': {vid2.video_path.path.name: {'favorite': favorite}},
    }

    # Save config, verify that favorite is set.
    save_channels_config()
    config = get_config()
    assert config['favorites'] == favorites

    def import_and_verify(favorited_ids: List[int]):
        with mock.patch('modules.videos.common.get_channel_source_id', lambda i: 'foo'):
            import_videos_config()
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
    config = get_config()
    assert config['favorites'] == favorites
    import_and_verify([vid3.id])

    # Add vid2 again, it should be favorited on import.
    vid2 = Video(video_path=vid2_video_path)
    test_session.add(vid2)
    test_session.commit()
    import_and_verify([vid3.id, vid2.id])

    # Deleting the Video in the model really removes the favorite status.
    vid3.delete()
    config = get_config()
    assert config['favorites'] == {'NO CHANNEL': {vid2.video_path.path.name: {'favorite': favorite}}}
    import_and_verify([vid2.id])
