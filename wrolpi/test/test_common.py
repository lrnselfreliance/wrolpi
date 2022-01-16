import os
import pathlib
import tempfile
import unittest
from datetime import date, datetime

import pytest
from sanic_openapi import doc

from wrolpi.common import combine_dicts, insert_parameter, date_range, api_param_limiter, chdir
from wrolpi.dates import set_timezone, now
from wrolpi.errors import NoBodyContents, MissingRequiredField, ExcessJSONFields, InvalidTimezone
from wrolpi.schema import validate_data
from wrolpi.test.common import build_test_directories, wrap_media_directory


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
    with wrap_media_directory():
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


@pytest.mark.parametrize(
    'i,expected', [
        (1, 1),
        (100, 100),
        (150, 100),
        (-1, -1),
        (-1.0, -1.0),
        (1.0, 1.0),
        (100.0, 100.0),
        (150.0, 100.0),
        ('1', 1),
        (None, 20),
        (0, 20),
        (0.0, 20),
        ('', 20),
    ]
)
def test_api_param_limiter(i, expected):
    limiter = api_param_limiter(100)  # should never return an integer greater than 100.
    assert limiter(i) == expected


def test_chdir():
    """
    The current working directory can be changed temporarily using the `chdir` context manager.
    """
    original = os.getcwd()
    home = os.environ.get('HOME')
    assert home

    with chdir():
        assert os.getcwd() != original
        assert str(os.getcwd()).startswith('/tmp')
        assert os.environ['HOME'] != os.getcwd()
    # Replace $HOME
    with chdir(with_home=True):
        assert os.getcwd() != original
        assert str(os.getcwd()).startswith('/tmp')
        assert os.environ['HOME'] == os.getcwd()

    with tempfile.TemporaryDirectory() as d:
        # Without replacing $HOME
        with chdir(pathlib.Path(d), with_home=True):
            assert os.getcwd() == d
            assert os.environ['HOME'] == os.getcwd()
        with chdir(pathlib.Path(d)):
            assert os.getcwd() == d
            assert os.environ['HOME'] != os.getcwd()
