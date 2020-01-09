from api.test.common import ExtendedTestCase
from api.videos.common import get_absolute_media_path


class TestCommon(ExtendedTestCase):

    def test_get_absolute_media_path(self):
        blender = get_absolute_media_path('videos/blender')
        assert str(blender).endswith('blender')
