import os
import pathlib
import tempfile
import unittest
from datetime import date, datetime
from decimal import Decimal

import pytest

from wrolpi.common import insert_parameter, date_range, api_param_limiter, chdir, zig_zag, \
    escape_file_name
from wrolpi.dates import set_timezone, now
from wrolpi.errors import InvalidTimezone
from wrolpi.test.common import build_test_directories


def test_build_video_directories(test_directory):
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


@pytest.mark.parametrize('low,high,expected', [
    (0, 10000, [0, 5000, 2500, 7500, 1250, 3750, 6250, 8750, 625, 1875, 3125, 4375, 5625, 6875, 8125, 9375]),
    (0, 1000, [0, 500, 250, 750, 125, 375, 625, 875, 62, 187, 312, 437, 562, 687, 812, 937]),
    (0, 100, [0, 50, 25, 75, 12, 37, 62, 87, 6, 18, 31, 43, 56, 68, 81, 93]),
    # Values repeat when there are not enough.
    (0, 10, [0, 5, 2, 7, 1, 3, 6, 8, 0, 1, 3, 4, 5, 6, 8, 9]),
    (0, 5, [0, 2, 1, 3, 0, 1, 3, 4]),
    (0, 2, [0, 1, 0, 1, 0, 0, 1, 1, 0, 0, 0, 0, 1, 1, 1, 1]),
    (50, 100, [50, 75, 62, 87, 56, 68, 81, 93, 53, 59, 65]),
    (8, 98, [8, 53, 30, 75, 19, 41, 64]),
    # Floats are supported.  Output is identical to above.
    (50.0, 100.0, [50.0, 75.0, 62.5, 87.5, 56.25, 68.75, 81.25, 93.75, 53.125, 59.375, 65.625]),
    # Decimals are supported.  Output is identical to above.
    (Decimal('50.0'), Decimal('100.0'), [
        Decimal('50'), Decimal('75'), Decimal('62.5'), Decimal('87.5'), Decimal('56.25'), Decimal('68.75'),
        Decimal('81.25'), Decimal('93.75'), Decimal('53.125'), Decimal('59.375'), Decimal('65.625')
    ]),
    # Datetimes are supported.
    (datetime(2000, 1, 1), datetime(2000, 1, 8), [
        datetime(2000, 1, 1), datetime(2000, 1, 4, 12), datetime(2000, 1, 2, 18), datetime(2000, 1, 6, 6),
        datetime(2000, 1, 1, 21), datetime(2000, 1, 3, 15),
    ])
])
def test_zig_zag(low, high, expected):
    zagger = zig_zag(low, high)
    for i in expected:
        result = next(zagger)
        assert result == i
        assert low <= result < high


@pytest.mark.parametrize(
    'name,expected', [
        ('', ''),
        ('foo', 'foo'),
        ('foo\\', 'foo'),
        ('foo/', 'foo'),
        ('foo<', 'foo'),
        ('foo>', 'foo'),
        ('foo:', 'foo'),
        ('foo|', 'foo'),
        ('foo"', 'foo'),
        ('foo?', 'foo'),
        ('foo*', 'foo'),
        ('foo&', 'foo&'),
    ]
)
def test_escape_file_name(name, expected):
    assert escape_file_name(name) == expected
