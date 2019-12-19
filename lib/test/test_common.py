import unittest
from pprint import pformat

import pytest
from sanic_openapi import doc

from lib.common import create_pagination_pages, create_pagination_dict, Pagination, validate_data
from lib.errors import NoBodyContents, MissingRequiredField, ExcessJSONFields


class TestCommon(unittest.TestCase):

    def test_create_pagination_pages(self):
        tests = [
            # no padding needed
            ((1, 5), [1, 2, 3, 4, 5]),
            ((1, 9), [1, 2, 3, 4, 5, 6, 7, 8, 9]),
            # Only need padding on the right, last page is included
            ((1, 12), [1, 2, 3, 4, 5, 6, 7, 8, 9, '..', 12]),
            ((1, 20), [1, 2, 3, 4, 5, 6, 7, 8, 9, '..', 20]),
            ((5, 20), [1, 2, 3, 4, 5, 6, 7, 8, 9, '..', 20]),
            # 2 and 12 are replaced with skips, but we meet the link limit requirement
            ((7, 12), [1, '..', 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]),
            ((7, 13), [1, '..', 3, 4, 5, 6, 7, 8, 9, 10, 11, '..', 13]),
            # Only need padding on the left
            ((15, 20), [1, '..', 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]),
            # Padding on both sides, first and last page are included
            ((9, 20), [1, '..', 5, 6, 7, 8, 9, 10, 11, 12, 13, '..', 20]),
            ((9, 20, 5), [1, '..', 7, 8, 9, 10, 11, '..', 20]),
            ((9, 20, 1), [1, '..', 9, '..', 20]),
            # 0 padding shouldn't happen, but required pages are visible
            ((9, 20, 0), [1, '..', 9, '..', 20]),
            # A small list of pages
            ((1, 1), [1]),
            ((1, 2), [1, 2]),
        ]
        for args, expected in tests:
            result = create_pagination_pages(*args)
            self.assertEqual(result, expected)

    def test_create_pagination_dict(self):
        self.maxDiff = None
        tests = [
            (
                # an example using `more` rather than specifying `total`
                (0, 20, True),
                Pagination(0, 20, True, None, 1, [
                    {'page': 1, 'sub_offset': 0, 'active': True},
                    {'page': 2, 'sub_offset': 20},
                ])
            ),
            (
                # more is False, should only be one link
                (0, 20, False),
                Pagination(0, 20, False, None, 1, [
                    {'page': 1, 'sub_offset': 0, 'active': True},
                ])
            ),
            (
                # No padding on the left
                (0, 20, None, 256),
                Pagination(0, 20, None, 256, 1, [
                    {'page': 1, 'sub_offset': 0, 'active': True},
                    {'page': 2, 'sub_offset': 20},
                    {'page': 3, 'sub_offset': 40},
                    {'page': 4, 'sub_offset': 60},
                    {'page': 5, 'sub_offset': 80},
                    {'page': 6, 'sub_offset': 100},
                    {'page': 7, 'sub_offset': 120},
                    {'page': 8, 'sub_offset': 140},
                    {'page': 9, 'sub_offset': 160},
                    {'page': '..', 'disabled': True},
                    {'page': 13, 'sub_offset': 240},
                ])
            ),
            (
                (80, 20, None, 256),
                Pagination(80, 20, None, 256, 5, [
                    {'page': 1, 'sub_offset': 0},
                    {'page': 2, 'sub_offset': 20},
                    {'page': 3, 'sub_offset': 40},
                    {'page': 4, 'sub_offset': 60},
                    {'page': 5, 'sub_offset': 80, 'active': True},
                    {'page': 6, 'sub_offset': 100},
                    {'page': 7, 'sub_offset': 120},
                    {'page': 8, 'sub_offset': 140},
                    {'page': 9, 'sub_offset': 160},
                    {'page': '..', 'disabled': True},
                    {'page': 13, 'sub_offset': 240},
                ])
            ),
            (
                # Padding on both sides
                (120, 20, None, 256),
                Pagination(120, 20, None, 256, 7, [
                    {'page': 1, 'sub_offset': 0},
                    {'page': '..', 'disabled': True},
                    {'page': 3, 'sub_offset': 40},
                    {'page': 4, 'sub_offset': 60},
                    {'page': 5, 'sub_offset': 80},
                    {'page': 6, 'sub_offset': 100},
                    {'page': 7, 'sub_offset': 120, 'active': True},
                    {'page': 8, 'sub_offset': 140},
                    {'page': 9, 'sub_offset': 160},
                    {'page': 10, 'sub_offset': 180},
                    {'page': 11, 'sub_offset': 200},
                    {'page': '..', 'disabled': True},
                    {'page': 13, 'sub_offset': 240},
                ])
            ),
            (
                # Padding on the left
                (240, 20, None, 256),
                Pagination(240, 20, None, 256, 13, [
                    {'page': 1, 'sub_offset': 0},
                    {'page': '..', 'disabled': True},
                    {'page': 5, 'sub_offset': 80},
                    {'page': 6, 'sub_offset': 100},
                    {'page': 7, 'sub_offset': 120},
                    {'page': 8, 'sub_offset': 140},
                    {'page': 9, 'sub_offset': 160},
                    {'page': 10, 'sub_offset': 180},
                    {'page': 11, 'sub_offset': 200},
                    {'page': 12, 'sub_offset': 220},
                    {'page': 13, 'sub_offset': 240, 'active': True},
                ])
            ),
        ]
        for args, expected in tests:
            result = create_pagination_dict(*args)
            msg = f'\n\nArgs: {args}\nResult: {pformat(result.links)}\nExpected: {pformat(expected.links)}'
            self.assertEqual(result, expected, msg=msg)


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
