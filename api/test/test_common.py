import tempfile
from pathlib import Path
from queue import Queue

import pytest
from PIL import Image
from sanic_openapi import doc

from api.api import api_app, attach_routes
from api.common import validate_data, combine_dicts, insert_parameter, FeedReporter
from api.db import get_db_context
from api.errors import NoBodyContents, MissingRequiredField, ExcessJSONFields
from api.test.common import create_db_structure, build_test_directories, wrap_test_db
from api.videos.common import convert_image, bulk_replace_invalid_posters

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

        with get_db_context() as (db_conn, db):
            Channel = db['channel']
            for channel_name in _structure:
                channel = Channel.get_one(name=channel_name)
                assert (tempdir / channel_name).is_dir()
                assert channel
                assert channel['directory'] == str(tempdir / channel_name)
                assert len(list(channel['videos'])) == len([i for i in _structure[channel_name] if i.endswith('mp4')])

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
    foo = Image.new('RGB', (25, 25), color='grey')

    with tempfile.TemporaryDirectory() as tempdir:
        tempdir = Path(tempdir)

        # Save the new image to "foo.webp", convert it to a JPEG at "foo.jpg".
        existing_image = tempdir / 'foo.webp'
        foo.save(existing_image)

        destination_image = tempdir / 'foo.jpg'
        assert not destination_image.is_file()

        convert_image(existing_image, destination_image)
        assert destination_image.is_file()
        assert existing_image.is_file()

        # Test deletion
        destination_image.unlink()
        assert not destination_image.is_file()
        convert_image(existing_image, destination_image, remove=True)
        assert destination_image.is_file()
        assert not existing_image.is_file()


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

    with get_db_context() as (db_conn, db):
        Video = db['video']
        vid2 = Video.get_one(poster_path='vid2.webp')

    video_ids = [vid2['id'], ]
    bulk_replace_invalid_posters(video_ids)

    with get_db_context() as (db_conn, db):
        Video = db['video']
        # Get the video by ID because it's poster is now a JPEG.
        vid2 = Video.get_one(id=vid2['id'])
        assert vid2['poster_path'] == 'vid2.jpg'
        assert all('webp' not in i['poster_path'] for i in Video.get_where())

    # Old webp was removed
    assert not webp.is_file()
    new_jpg = tempdir / 'channel2/vid2.jpg'
    assert new_jpg.is_file()
    with open(new_jpg, 'rb') as new_jpg_fh:
        # The converted image is the same as the other JPEG because both are black 25x25 pixel images.
        assert jpg_fh_contents == new_jpg_fh.read()


@pytest.mark.parametrize(
    'totals, progresses,messages',
    [
        (
                [25],
                [],
                [
                    {'message': 'foo', 'who': 0, 'progresses': [{'percent': 0, 'total': 25}]},
                    {'code': 'bar', 'progresses': [{'percent': 0, 'total': 25}]},
                    {'code': 'error', 'message': 'baz', 'progresses': [{'percent': 0, 'total': 25}]},
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
                    {'message': 'foo', 'who': 0, 'progresses': [{'percent': 0, 'total': 25}]},
                    {'code': 'bar', 'progresses': [{'percent': 0, 'total': 25}]},
                    {'progresses': [{'percent': 4, 'total': 25}]},
                    {'progresses': [{'percent': 8, 'total': 25}]},
                    {'progresses': [{'percent': 16, 'total': 25}]},
                    {'progresses': [{'percent': 32, 'total': 25}]},
                    {'progresses': [{'percent': 64, 'total': 25}]},
                    {'progresses': [{'percent': 100, 'total': 25}]},
                    {'code': 'error', 'message': 'baz', 'progresses': [{'percent': 100, 'total': 25}]},
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
                    {'message': 'foo', 'who': 0, 'progresses': [
                        {'percent': 0, 'total': 25},
                        {'percent': 0, 'total': 10},
                    ]},
                    {'code': 'bar', 'progresses': [
                        {'percent': 0, 'total': 25},
                        {'percent': 0, 'total': 10},
                    ]},
                    {'progresses': [
                        {'percent': 0, 'total': 25},
                        {'percent': 30, 'total': 10},
                    ]},
                    {'progresses': [
                        {'percent': 0, 'total': 25},
                        {'percent': 80, 'total': 10},
                    ]},
                    {'progresses': [
                        {'percent': 72, 'total': 25},
                        {'percent': 80, 'total': 10},
                    ]},
                    {'progresses': [
                        {'percent': 72, 'total': 25},
                        {'percent': 100, 'total': 10},
                    ]},
                    {'progresses': [
                        {'percent': 100, 'total': 25},
                        {'percent': 100, 'total': 10},
                    ]},
                    {
                        'code': 'error',
                        'message': 'baz', 'progresses': [{'percent': 100, 'total': 25}, {'percent': 100, 'total': 10}]
                    },
                ]
        ),
    ]
)
def test_feed_reporter(totals, progresses, messages):
    q = Queue()
    reporter = FeedReporter(q, len(totals))

    for idx, total in enumerate(totals):
        reporter.set_progress_total(idx, total)

    reporter.message(0, 'foo')
    reporter.code('bar')

    for progress in progresses:
        reporter.set_progress(*progress)

    reporter.error('baz')

    count = 0
    while not q.empty():
        received = q.get_nowait()
        try:
            message = messages.pop(0)
        except IndexError:
            raise AssertionError(f'Queue ({count}) had excess message: {received}')

        assert message == received, f'Message {count} did not match'

        count += 1
