from pathlib import Path

import pytest
from sanic_openapi import doc

from api.api import api_app, attach_routes
from api.common import validate_data, combine_dicts
from api.db import get_db_context
from api.errors import NoBodyContents, MissingRequiredField, ExcessJSONFields
# Attach the default routes
from api.test.common import create_db_structure, build_test_directories

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
