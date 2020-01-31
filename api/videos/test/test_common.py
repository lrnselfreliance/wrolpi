import pathlib
import tempfile

from api.test.common import ExtendedTestCase
from api.videos.common import get_absolute_media_path, get_matching_directories


class TestCommon(ExtendedTestCase):

    def test_get_absolute_media_path(self):
        blender = get_absolute_media_path('videos/blender')
        assert str(blender).endswith('blender')

    def test_matching_directories(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = pathlib.Path(temp_dir)
            # Directories
            foo = temp_dir / 'foo'
            foo.mkdir()
            qux = foo / 'qux'
            qux.mkdir()

            bar = temp_dir / 'bar'
            bar.mkdir()
            baz = temp_dir / 'baz'
            baz.mkdir()

            # These files should never be returned
            (temp_dir / 'barr').touch()
            (temp_dir / 'bazz').touch()

            # Get all directories starting with f
            matches = get_matching_directories(temp_dir / 'f')
            assert matches == [str(temp_dir / 'foo')]

            # Get all directories starting with b
            matches = get_matching_directories(temp_dir / 'b')
            assert matches == [str(temp_dir / 'bar'), str(temp_dir / 'baz')]

            # No directories have c
            matches = get_matching_directories(temp_dir / 'c')
            assert matches == []

            # foo is an exact match, return subdirectories
            matches = get_matching_directories(temp_dir / 'foo')
            assert matches == [str(foo / 'qux')]
