from functools import wraps
from queue import Queue

from modules.videos.lib import refresh_channel_videos
from modules.videos.models import Channel
from wrolpi.common import ProgressReporter, insert_parameter
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
            # Dummy queue and reporter to receive messages.
            q = Queue()
            reporter = ProgressReporter(q, 2)

            # Convert the channel/video structure to a file structure for the test.
            file_structure = []
            for channel, paths in structure.items():
                for path in paths:
                    file_structure.append(f'{channel}/{path}')
                file_structure.append(f'{channel}/')

            with build_test_directories(file_structure) as tempdir:
                args, kwargs = insert_parameter(func, 'tempdir', tempdir, args, kwargs)

                with get_db_session(commit=True) as session:
                    for channel in structure:
                        channel_ = Channel(directory=str(tempdir / channel), name=channel, link=channel)
                        session.add(channel_)
                        session.flush()
                        session.refresh(channel_)

                with get_db_session(commit=True) as session:
                    for channel_ in session.query(Channel).all():
                        refresh_channel_videos(channel_, reporter)

                return func(*args, **kwargs)

        return wrapped

    return wrapper
