import json
import os
import pathlib
import tempfile
from contextlib import contextmanager
from functools import partialmethod
from itertools import zip_longest
from typing import List

import mock
import pytest

from wrolpi.api_utils import CustomJSONEncoder
from wrolpi.common import get_media_directory
from wrolpi.conftest import test_db, test_client  # noqa
from wrolpi.db import postgres_engine
from wrolpi.vars import CIRCLECI, IS_MACOS

TEST_CONFIG_PATH = tempfile.NamedTemporaryFile(mode='rt', delete=False)

skip_circleci = pytest.mark.skipif(CIRCLECI, reason='This test is not supported in Circle CI')
skip_macos = pytest.mark.skipif(IS_MACOS, reason='This test is not supported on MacOS')
only_macos = pytest.mark.skipif(not IS_MACOS, reason='This test is only supported on MacOS')


def wrap_test_db(func):
    """
    Wrap a test so that when calling wrolpi.common.get_db, it returns a testing database cloned from the api
    template.
    """

    def wrapped(*a, **kw):
        test_engine, session = test_db()

        def fake_get_db_session():
            """Get the testing db"""
            return test_engine, session

        try:
            with mock.patch('wrolpi.db._get_db_session', fake_get_db_session):
                # Run the test.
                result = func(*a, **kw)
                return result
        finally:
            session.rollback()
            session.close()
            test_engine.dispose()
            conn = postgres_engine.connect()
            conn.execute(f'DROP DATABASE IF EXISTS {test_engine.engine.url.database}')

    return wrapped


class PytestCase:
    """
    Replicate unittest.TestCase methods to bridge the gap between it and Pytest.
    """

    @staticmethod
    def assertGreater(a, b, msg: str = None):  # noqa
        assert a > b, msg

    @staticmethod
    def assertLess(a, b, msg: str = None):  # noqa
        assert a < b, msg

    @staticmethod
    def assertEqual(a, b, msg: str = None):  # noqa
        assert a == b, msg or f'{a} != {b}'

    @staticmethod
    def assertRaises(exception, func, *args, **kwargs):  # noqa
        try:
            func(*args, **kwargs)
        except exception:
            pass

    @classmethod
    def assertDictContains(cls, d1: dict, d2: dict):  # noqa
        assert_dict_contains(d1, d2)

    def assertError(self, response, http_status: int, code=None):  # noqa
        self.assertEqual(response.status_code, http_status)
        if code:
            self.assertEqual(response.json['code'], code)

    @staticmethod
    def assertTruth(value, expected):  # noqa
        """
        Check that a value is Truthy or Falsy.
        """
        if expected is True:
            assert value, f'Value {value} should have been truthy'
        else:
            assert not value, f'Value {value} should have been falsey'

    assertTruthy = partialmethod(assertTruth, expected=True)
    assertFalsey = partialmethod(assertTruth, expected=False)

    def assertItemsTruthyOrFalsey(self, items_list: List, expected_list: List):
        for d1, d2 in zip_longest(items_list, expected_list):
            for d2_key in d2:
                if d1 is None:
                    raise ValueError('d1 is None')
                if d2 is None:
                    raise ValueError('d2 is None')
                self.assertTruth(d1[d2_key], d2[d2_key])

    @staticmethod
    def assertLength(a, b):  # noqa
        assert len(a) == len(b), f'{len(a)=} != {len(b)=}'


@contextmanager
def build_test_directories(paths: List[str], tmp_dir: pathlib.Path = None) -> pathlib.Path:
    """
    Create directories based on the provided structure.

    Example:
        >>> build_test_directories([
                'channel1/vid1.mp4',
                'channel2/vid1.mp4',
                'channel2/vid2.mp4',
                'channel2/vid2.en.vtt'
            ])

        Creates directories like so:
            channel1/vid1.mp4
            channel2/vid1.mp4
            channel2/vid2.mp4
            channel2/vid2.en.vtt
    """
    tmp_dir = tmp_dir or get_media_directory()

    directories = filter(lambda i: i.endswith('/'), paths)
    for directory in directories:
        (tmp_dir / directory).mkdir(parents=True)

    files = filter(lambda i: not i.endswith('/'), paths)
    for file in files:
        file = tmp_dir / file
        parents = file.parents
        parents[0].mkdir(parents=True, exist_ok=True)
        (tmp_dir / file).touch()

    yield tmp_dir.absolute()


def assert_dict_contains(d1: dict, d2: dict):
    if hasattr(d1, '__dict__'):
        d1 = d1.__dict__
    if hasattr(d2, '__dict__'):
        d2 = d2.__dict__

    # Sort items so error is easier to read.
    d1 = dict(sorted(d1.items()))
    d2 = dict(sorted(d2.items()))

    for k2 in d2.keys():
        try:
            assert d1, f'dict 1 is empty: {d1}'
            assert d2, f'dict 1 is empty: {d2}'
            assert k2 in d1, f'dict 1 does not contain {k2}'
            if isinstance(d1[k2], dict):
                assert_dict_contains(d1[k2], d2[k2])
            else:
                assert d1[k2] == d2[k2], f'{repr(k2)} of value {repr(d1[k2])} does not equal {repr(d2[k2])} in dict 1'
        except AssertionError as e:
            d1_str = json.dumps(d1, indent=1, cls=CustomJSONEncoder)
            d2_str = json.dumps(d2, indent=1, cls=CustomJSONEncoder)
            raise AssertionError(f'{d1_str}\n\n{d2_str}\n\nDictionaries above are unequal') from e
