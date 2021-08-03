import pathlib

import pytest

from api.test.common import ExtendedTestCase, build_test_directories
from api.videos.common import get_absolute_media_path, get_matching_directories, remove_duplicate_video_paths


class TestCommon(ExtendedTestCase):

    def test_get_absolute_media_path(self):
        wrolpi = get_absolute_media_path('videos/wrolpi')
        assert str(wrolpi).endswith('wrolpi')

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
