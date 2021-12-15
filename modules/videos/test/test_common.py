import pathlib
import subprocess
import tempfile
from unittest import mock
from unittest.mock import Mock, MagicMock

import pytest
from PIL import Image

from modules.videos.models import Channel, Video
from modules.videos.test.common import create_channel_structure
from wrolpi.common import get_absolute_media_path
from wrolpi.db import get_db_session
from wrolpi.test.common import build_test_directories, wrap_test_db, TestAPI
from wrolpi.vars import PROJECT_DIR
from ..common import get_matching_directories, convert_image, bulk_validate_posters, remove_duplicate_video_paths, \
    update_view_count, get_video_duration


class TestCommon(TestAPI):

    def test_get_absolute_media_path(self):
        path = get_absolute_media_path('videos')
        self.assertTrue(str(path).endswith('videos'))

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

    def test_get_video_duration(self):
        """
        Video duration can be retrieved from the video file.
        """
        video_path = PROJECT_DIR / 'test/big_buck_bunny_720p_1mb.mp4'
        self.assertEqual(get_video_duration(video_path), 5)

        video_path = PROJECT_DIR / 'test/does not exist.mp4'
        self.assertRaises(FileNotFoundError, get_video_duration, video_path)

        video_path = str(PROJECT_DIR / 'test/does not exist.mp4')
        self.assertRaises(FileNotFoundError, get_video_duration, video_path)

        with tempfile.NamedTemporaryFile() as fh:
            self.assertRaises(subprocess.CalledProcessError, get_video_duration, fh.name)


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
    update_view_count(channel1.id)
    check_view_counts({'vid1.mp4': 10, 'vid2.mp4': None, 'vid3.mp4': None, 'vid4.mp4': None})

    # Channel 2 is updated, the other channels are left alone.  The 'bad_id' video is ignored.
    update_view_count(channel2.id)
    check_view_counts({'vid1.mp4': 10, 'vid2.mp4': 11, 'vid3.mp4': None, 'vid4.mp4': None})

    # All videos are updated.
    update_view_count(channel3.id)
    check_view_counts({'vid1.mp4': 10, 'vid2.mp4': 11, 'vid3.mp4': 13, 'vid4.mp4': 14})

    # An outdated view count will be overwritten.
    with get_db_session(commit=True) as session:
        vid = session.query(Video).filter_by(id=1).one()
        vid.view_count = 8
    check_view_counts({'vid1.mp4': 8, 'vid2.mp4': 11, 'vid3.mp4': 13, 'vid4.mp4': 14})
    update_view_count(channel1.id)
    check_view_counts({'vid1.mp4': 10, 'vid2.mp4': 11, 'vid3.mp4': 13, 'vid4.mp4': 14})
