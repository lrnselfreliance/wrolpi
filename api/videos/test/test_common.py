import pathlib
import tempfile

from api.db import get_db_context
from api.test.common import ExtendedTestCase, wrap_test_db, create_db_structure
from api.videos.common import get_absolute_media_path, get_matching_directories, delete_video


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

            bar = temp_dir / 'Bar'
            bar.mkdir()
            baz = temp_dir / 'baz'
            baz.mkdir()

            # These are files, and should never be returned
            (temp_dir / 'barr').touch()
            (temp_dir / 'bazz').touch()
            (baz / 'baz').touch()

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
            assert matches == [str(foo / 'qux')]

    @wrap_test_db
    @create_db_structure({
        'channel1': [
            'vid1.mp4',
            'vid1.en.vtt',
        ],
        'channel2': [
            'vid2.mp4',
            'vid2.info.json',
        ],
    })
    def test_delete_video(self, tempdir):
        with get_db_context(commit=True) as (db_conn, db):
            Channel, Video = db['channel'], db['video']

            channel1 = Channel.get_one(name='channel1')
            channel2 = Channel.get_one(name='channel2')
            vid1, vid2 = Video.get_where().order_by('video_path ASC')

            # No videos have been deleted yet.
            self.assertIsNone(channel1['skip_download_videos'])
            self.assertIsNone(channel2['skip_download_videos'])
            self.assertTrue((tempdir / 'channel1/vid1.mp4').is_file())

            delete_video(vid1)

            channel1 = Channel.get_one(id=channel1['id'])
            # Video was added to skip list.
            self.assertEqual(len(channel1['skip_download_videos']), 1)
            # Deleting a video leaves it's entry in the DB, but its files are deleted.
            self.assertEqual(Video.count(), 2)
            self.assertFalse((tempdir / 'channel1/vid1.mp4').is_file())
            self.assertTrue((tempdir / 'channel2/vid2.mp4').is_file())

            delete_video(vid2)

            self.assertEqual(Video.count(), 2)
            self.assertFalse((tempdir / 'channel1/vid1.mp4').is_file())
            self.assertFalse((tempdir / 'channel2/vid2.mp4').is_file())

            # A video can be deleted again.  This is because its only marked as deleted.
            delete_video(vid2)
