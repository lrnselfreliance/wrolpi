import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from queue import Queue
from unittest import mock
from unittest.mock import Mock

import pytest
from PIL import Image
from sanic_openapi import doc

from api.api import api_app, attach_routes
from api.common import validate_data, combine_dicts, insert_parameter, ProgressReporter, date_range
from api.db import get_db_context
from api.errors import NoBodyContents, MissingRequiredField, ExcessJSONFields
from api.test.common import create_db_structure, build_test_directories, wrap_test_db
from api.videos.common import convert_image, bulk_validate_posters
from api.videos.models import Video, Channel

# Attach the default routes
attach_routes(api_app)


class Model:
    name = doc.String(required=True)
    count = doc.Integer(required=True)
    fish = doc.Tuple()
    on = doc.Boolean()
    obj = doc.Dictionary()
    many = doc.Float()


@pytest.mark.parametrize(
    'data,expected',
    (
            (
                    dict(name='foo', count='4'),
                    dict(name='foo', count=4),
            ),
            (
                    dict(name='foo', count=4, fish=['red', 'blue'], on='false'),
                    dict(name='foo', count=4, fish=('red', 'blue'), on=False),
            ),
            (
                    dict(name='foo', count=4, fish=['red', 'blue'], on='true'),
                    dict(name='foo', count=4, fish=('red', 'blue'), on=True),
            ),
            (
                    dict(name='foo', count=4, fish=['red', 'blue'], on='t'),
                    dict(name='foo', count=4, fish=('red', 'blue'), on=True),
            ),
            (
                    dict(name='foo', count=4, fish=['red', 'blue'], on=1),
                    dict(name='foo', count=4, fish=('red', 'blue'), on=True),
            ),
            (
                    dict(name='foo', count=1.5, obj={'foo': 'bar'}),
                    dict(name='foo', count=1, obj={'foo': 'bar'}),
            ),
            (
                    dict(name='foo', count=1.5, many='10.3'),
                    dict(name='foo', count=1, many=10.3),
            ),
    )
)
def test_validate_doc(data, expected):
    model = Model()
    result = validate_data(model, data)
    assert result == expected


@pytest.mark.parametrize(
    'data,expected',
    (
            (dict(), NoBodyContents),
            (dict(name='foo'), MissingRequiredField),
            (dict(name='foo', count=10, extra='too many'), ExcessJSONFields),
    )
)
def test_validate_doc_errors(data, expected):
    model = Model()
    pytest.raises(expected, validate_data, model, data)


@pytest.mark.parametrize(
    'data,expected',
    (
            (
                    [dict()],
                    dict()
            ), (
                    [dict(a='b')],
                    dict(a='b')
            ), (
                    [dict(a='b'), dict(b='c')],
                    dict(a='b', b='c')
            ), (
                    [dict(b='c'), dict(a='b')],
                    dict(a='b', b='c'),
            ), (
                    [dict(a=dict(b='c'), d='e'), dict(a=(dict(f='g')))],
                    dict(a=dict(b='c', f='g'), d='e'),
            ), (
                    [dict(a=dict(b='c'), d='e'), dict(a=(dict(b='g')))],
                    dict(a=dict(b='c'), d='e'),
            ), (
                    [dict(a=dict(b='c'), d=[1, 2, 3]), dict(a=(dict(b='g')))],
                    dict(a=dict(b='c'), d=[1, 2, 3]),
            ), (
                    [dict(a='b', c=dict(d='e')), dict(a='c', e='f')],
                    dict(a='b', c=dict(d='e'), e='f')
            ), (
                    [dict(a='b'), dict(a='c', d='e'), dict(e='f', a='d')],
                    dict(a='b', d='e', e='f')
            ), (
                    [dict(a='b'), dict(), dict(e='f', a='d')],
                    dict(a='b', e='f')
            )
    )
)
def test_combine_dicts(data, expected):
    assert combine_dicts(*data) == expected


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
    @create_db_structure(_structure)
    def test_func(tempdir):
        assert isinstance(tempdir, Path)
        for path in paths:
            path = (tempdir / path)
            assert path.exists()
            assert path.is_file()

        with get_db_context() as (engine, session):
            for channel_name in _structure:
                channel = session.query(Channel).filter_by(name=channel_name).one()
                assert (tempdir / channel_name).is_dir()
                assert channel
                assert channel.directory == tempdir / channel_name
                assert len(channel.videos) == len([i for i in _structure[channel_name] if i.endswith('mp4')])

    test_func()


def test_build_video_directories():
    structure = [
        'channel1/vid1.mp4',
    ]
    with build_test_directories(structure) as tempdir:
        assert (tempdir / 'channel1').is_dir()
        assert (tempdir / 'channel1/vid1.mp4').is_file()

    structure = [
        'channel2/',
        'channel2.1/channel2.2/',
    ]
    with build_test_directories(structure) as tempdir:
        assert (tempdir / 'channel2').is_dir()
        assert (tempdir / 'channel2.1/channel2.2').is_dir()

    structure = [
        'channel3/vid1.mp4',
        'channel3/vid2.mp4',
        'channel4/vid1.mp4',
        'channel4/vid1.en.vtt',
        'channel5/',
    ]
    with build_test_directories(structure) as tempdir:
        assert (tempdir / 'channel3/vid1.mp4').is_file()
        assert (tempdir / 'channel3').is_dir()
        assert (tempdir / 'channel3/vid2.mp4').is_file()
        assert (tempdir / 'channel4/vid1.mp4').is_file()
        assert (tempdir / 'channel4/vid1.en.vtt').is_file()
        assert (tempdir / 'channel5').is_dir()

    structure = [
        'channel6/subdirectory/vid1.mp4',
    ]
    with build_test_directories(structure) as tempdir:
        assert (tempdir / 'channel6/subdirectory').is_dir()
        assert (tempdir / 'channel6/subdirectory/vid1.mp4').is_file()


def test_insert_parameter():
    """
    A convenience function exists that inserts a parameter or keyword argument into the provided args/kwargs,
    wherever that may be according to the function's signature.
    """

    def func(foo, bar):
        pass

    results = insert_parameter(func, 'bar', 'bar', (1,), {})
    assert results == ((1, 'bar'), {})

    def func(foo, bar, baz):
        pass

    results = insert_parameter(func, 'bar', 'bar', (1, 2), {})
    assert results == ((1, 'bar', 2), {})

    def func(foo, baz, bar=None):
        pass

    results = insert_parameter(func, 'bar', 'bar', (1, 2), {})
    assert results == ((1, 2, 'bar'), {})

    def func(foo, baz, bar=None):
        pass

    results = insert_parameter(func, 'baz', 'baz', (1, 2), {})
    assert results == ((1, 'baz', 2), {})

    def func(foo, baz, qux=None, bar=None):
        pass

    results = insert_parameter(func, 'bar', 'bar', (1, 2, 3), {})
    assert results == ((1, 2, 3, 'bar'), {})

    # bar is not defined as a parameter!
    def func(foo):
        pass

    pytest.raises(TypeError, insert_parameter, func, 'bar', 'bar', (1,), {})


def test_convert_image():
    """
    An image's format can be changed.  This tests that convert_image() converts from a WEBP format, to a JPEG format.
    """
    foo = Image.new('RGB', (25, 25), color='grey')

    with tempfile.TemporaryDirectory() as tempdir:
        tempdir = Path(tempdir)

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


@wrap_test_db
@create_db_structure(
    {
        'channel1': ['vid1.mp4', 'vid1.jpg'],
        'channel2': ['vid2.flv', 'vid2.webp'],
    }
)
def test_bulk_replace_invalid_posters(tempdir: Path):
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

    with get_db_context() as (engine, session):
        vid1 = session.query(Video).filter_by(poster_path='vid1.jpg').one()
        assert vid1.validated_poster is False

        vid2 = session.query(Video).filter_by(poster_path='vid2.webp').one()
        assert vid2.validated_poster is False

    # Convert the WEBP image.  convert_image() should only be called once.
    mocked_convert_image = Mock(wraps=convert_image)
    with mock.patch('api.videos.common.convert_image', mocked_convert_image):
        video_ids = [vid1.id, vid2.id]
        bulk_validate_posters(video_ids)

    mocked_convert_image.assert_called_once_with(webp, tempdir / 'channel2/vid2.jpg')

    with get_db_context() as (engine, session):
        # Get the video by ID because it's poster is now a JPEG.
        vid2 = session.query(Video).filter_by(id=vid2.id).one()
        assert str(vid2.poster_path) == 'vid2.jpg'
        assert all('webp' not in str(i.poster_path) for i in session.query(Video).all())
        assert vid2.validated_poster is True

        # Vid1's image was validated, but not converted.
        vid1 = session.query(Video).filter_by(id=vid1.id).one()
        assert str(vid1.poster_path) == 'vid1.jpg'
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
    with mock.patch('api.videos.common.convert_image', mocked_convert_image):
        video_ids = [vid1.id, vid2.id]
        bulk_validate_posters(video_ids)

    mocked_convert_image.assert_not_called()


@pytest.mark.parametrize(
    'totals,progresses,messages',
    [
        (
                [25],
                [],
                [
                    {'progresses': [dict(message='foo', percent=0, total=25, value=0)]},
                    {'code': 'bar', 'progresses': [dict(message='foo', percent=0, total=25, value=0)]},
                    {'code': 'error', 'progresses': [dict(message='baz', percent=0, total=25, value=0)]},
                ],
        ),
        (
                [25],
                [
                    (0, 1),
                    (0, 2),
                    (0, 4),
                    (0, 8),
                    (0, 16),
                    (0, 25),
                ],
                [
                    {'progresses': [dict(message='foo', percent=0, total=25, value=0)]},
                    {'code': 'bar', 'progresses': [dict(message='foo', percent=0, total=25, value=0)]},
                    {'progresses': [dict(message='foo', percent=4, total=25, value=1)]},
                    {'progresses': [dict(message='foo', percent=8, total=25, value=2)]},
                    {'progresses': [dict(message='foo', percent=16, total=25, value=4)]},
                    {'progresses': [dict(message='foo', percent=32, total=25, value=8)]},
                    {'progresses': [dict(message='foo', percent=64, total=25, value=16)]},
                    {'progresses': [dict(message='foo', percent=100, total=25, value=25)]},
                    {'code': 'error', 'progresses': [dict(message='baz', percent=100, total=25, value=25)]},
                ]
        ),
        (
                [25, 10],
                [
                    (1, 3),
                    (1, 8),
                    (0, 18),
                    (1, 10),
                    (0, 30),  # This is higher than the total of 25, percent should be 100.
                ],
                [
                    {'progresses': [
                        dict(message='foo', percent=0, total=25, value=0),
                        dict(percent=0, total=10, value=0),
                    ]},
                    {'code': 'bar', 'progresses': [
                        dict(message='foo', percent=0, total=25, value=0),
                        dict(percent=0, total=10, value=0),
                    ]},
                    {'progresses': [
                        dict(message='foo', percent=0, total=25, value=0),
                        dict(percent=30, total=10, value=3),
                    ]},
                    {'progresses': [
                        dict(message='foo', percent=0, total=25, value=0),
                        dict(percent=80, total=10, value=8),
                    ]},
                    {'progresses': [
                        dict(message='foo', percent=72, total=25, value=18),
                        dict(percent=80, total=10, value=8),
                    ]},
                    {'progresses': [
                        dict(message='foo', percent=72, total=25, value=18),
                        dict(percent=100, total=10, value=10),
                    ]},
                    {'progresses': [
                        dict(message='foo', percent=100, total=25, value=30),
                        dict(percent=100, total=10, value=10),
                    ]},
                    {
                        'code': 'error',
                        'progresses': [
                            dict(message='baz', percent=100, total=25, value=30),
                            dict(percent=100, total=10, value=10),
                        ]
                    },
                ]
        ),
    ]
)
def test_feed_reporter(totals, progresses, messages):
    q = Queue()
    reporter = ProgressReporter(q, len(totals))

    for idx, total in enumerate(totals):
        reporter.set_progress_total(idx, total)

    reporter.message(0, 'foo')
    reporter.code('bar')

    for progress in progresses:
        reporter.send_progress(*progress)

    reporter.error(0, 'baz')

    count = 0
    while not q.empty():
        received = q.get_nowait()
        try:
            message = messages.pop(0)
        except IndexError:
            raise AssertionError(f'Queue ({count}) had excess message: {received}')

        assert message == received, f'Message {count} did not match'

        count += 1


def test_feed_reporter_finish():
    q = Queue()
    reporter = ProgressReporter(q)

    reporter.set_progress_total(0, 50)
    reporter.send_progress(0, 0)
    reporter.send_progress(0, 20)
    reporter.finish(0, 'completed')

    expected = [
        {'progresses': [{'percent': 0, 'total': 50, 'value': 0}]},
        {'progresses': [{'percent': 40, 'total': 50, 'value': 20}]},
        {'progresses': [{'message': 'completed', 'percent': 100, 'value': 50, 'total': 50}]},
    ]

    count = 0

    while not q.empty():
        received = q.get_nowait()
        try:
            message = expected.pop(0)
        except IndexError:
            raise AssertionError(f'Queue ({count}) had excess message: {received}')

        assert message == received, f'Message {count} did not match'

        count += 1


class TestCommon(unittest.TestCase):

    def test_date_range(self):
        # A single step results in the start.
        result = date_range(date(1970, 1, 1), date(1970, 1, 2), 1)
        assert result == [
            date(1970, 1, 1),
        ]

        # Many steps on a single day results in the same day.
        result = date_range(date(1970, 1, 1), date(1970, 1, 1), 5)
        assert result == [
            date(1970, 1, 1),
            date(1970, 1, 1),
            date(1970, 1, 1),
            date(1970, 1, 1),
            date(1970, 1, 1),
        ]

        # Many steps on a single datetime results in a range of times.
        result = date_range(datetime(1970, 1, 1), datetime(1970, 1, 1, 23, 59, 59), 5)
        assert result == [
            datetime(1970, 1, 1, 0, 0),
            datetime(1970, 1, 1, 4, 47, 59, 800000),
            datetime(1970, 1, 1, 9, 35, 59, 600000),
            datetime(1970, 1, 1, 14, 23, 59, 400000),
            datetime(1970, 1, 1, 19, 11, 59, 200000),
        ]

        # date_range is not inclusive, like range().
        result = date_range(date(1970, 1, 1), date(1970, 1, 5), 4)
        assert result == [
            date(1970, 1, 1),
            date(1970, 1, 2),
            date(1970, 1, 3),
            date(1970, 1, 4),
        ]

        # Reversed dates are supported.
        result = date_range(date(1970, 1, 5), date(1970, 1, 1), 4)
        assert result == [
            date(1970, 1, 5),
            date(1970, 1, 4),
            date(1970, 1, 3),
            date(1970, 1, 2),
        ]

        # Large date spans are supported.
        result = date_range(date(1970, 1, 1), date(2020, 5, 1), 4)
        assert result == [
            date(1970, 1, 1),
            date(1982, 8, 1),
            date(1995, 3, 2),
            date(2007, 10, 1),
        ]

        result = date_range(datetime(1970, 1, 1, 0, 0, 0), datetime(1970, 1, 1, 10, 0), 8)
        assert result == [
            datetime(1970, 1, 1, 0, 0),
            datetime(1970, 1, 1, 1, 15),
            datetime(1970, 1, 1, 2, 30),
            datetime(1970, 1, 1, 3, 45),
            datetime(1970, 1, 1, 5, 0),
            datetime(1970, 1, 1, 6, 15),
            datetime(1970, 1, 1, 7, 30),
            datetime(1970, 1, 1, 8, 45),
        ]

        # More steps than days
        result = date_range(date(1970, 1, 1), date(1970, 1, 7), 10)
        assert result == [
            date(1970, 1, 1),
            date(1970, 1, 1),
            date(1970, 1, 2),
            date(1970, 1, 2),
            date(1970, 1, 3),
            date(1970, 1, 4),
            date(1970, 1, 4),
            date(1970, 1, 5),
            date(1970, 1, 5),
            date(1970, 1, 6),
        ]
