import pytest
from sanic_openapi import doc

from lib.common import validate_data
from lib.errors import NoBodyContents, MissingRequiredField, ExcessJSONFields


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
