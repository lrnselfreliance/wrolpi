import pathlib
import tempfile
from functools import wraps

from modules.videos.lib import refresh_channel_videos
from modules.videos.models import Channel
from wrolpi.common import insert_parameter, set_test_media_directory
from wrolpi.db import get_db_session
from wrolpi.test.common import wrap_test_db, build_test_directories


def create_channel_structure(structure):
    """
    Create a directory containing the specified structure of channels and videos.  Create DB entries for these
    channels and videos.

    Example:
        >>> s = {'channel1': ['vid1.mp4'], 'channel2': ['vid1.mp4', 'vid2.mp4', 'vid2.en.vtt']}
        >>> create_channel_structure(s)

        Creates directories like so:
            channel1/vid1.mp4
            channel2/vid1.mp4
            channel2/vid2.mp4
            channel2/vid2.en.vtt

        Channels like so:
            Channel(name='channel1', directory='channel1')
            Channel(name='channel2', directory='channel2')

        And, Videos like so:
            Video(channel_id=1, video_path='vid1.mp4')
            Video(channel_id=2, video_path='vid1.mp4')
            Video(channel_id=2, video_path='vid2.mp4', caption_path='vid2.en.vtt')
    """

    def wrapper(func):
        @wraps(func)
        @wrap_test_db
        def wrapped(*args, **kwargs):
            if args and (test := args[0]) and hasattr(test, 'tmp_dir'):
                tmp_dir = pathlib.Path(test.tmp_dir.name)
            else:
                tmp_dir = pathlib.Path(tempfile.TemporaryDirectory().name)
                set_test_media_directory(tmp_dir)

            # Convert the channel/video structure to a file structure for the test.
            file_structure = []
            for channel, paths in structure.items():
                for path in paths:
                    file_structure.append(f'{channel}/{path}')
                file_structure.append(f'{channel}/')

            with build_test_directories(file_structure, tmp_dir) as tempdir:
                args, kwargs = insert_parameter(func, 'tempdir', tempdir, args, kwargs)

                with get_db_session(commit=True) as session:
                    for channel in structure:
                        channel_ = Channel(directory=str(tempdir / channel), name=channel, link=channel)
                        session.add(channel_)
                        session.flush()
                        session.refresh(channel_)

                with get_db_session(commit=True) as session:
                    for channel_ in session.query(Channel).all():
                        refresh_channel_videos(channel_)

                try:
                    return func(*args, **kwargs)
                finally:
                    set_test_media_directory(None)

        return wrapped

    return wrapper
