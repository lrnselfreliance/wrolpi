import unittest
from datetime import date, datetime
from queue import Queue

import pytest
from sanic_openapi import doc

from wrolpi.common import combine_dicts, insert_parameter, ProgressReporter, date_range
from wrolpi.dates import set_timezone, now
from wrolpi.errors import NoBodyContents, MissingRequiredField, ExcessJSONFields, InvalidTimezone
from wrolpi.schema import validate_data
from wrolpi.test.common import build_test_directories, wrap_test_db


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

    def test_set_timezone(self):
        """
        The global timezone can be changed.  Invalid timezones are rejected.
        """
        original_timezone = now().tzinfo

        try:
            self.assertRaises(InvalidTimezone, set_timezone, '')
            self.assertEqual(now().tzinfo, original_timezone)

            set_timezone('US/Pacific')
            self.assertNotEqual(now().tzinfo, original_timezone)
        finally:
            # Restore the timezone before the test.
            set_timezone(original_timezone)
