"""What is left of the API's side of a secondary's sync: its settings, and the primary's folders it may exclude.
The sync itself is the Controller's (controller/test/test_sync.py)."""
from collections import namedtuple

import pytest

from wrolpi.common import set_test_media_directory
from wrolpi.errors import InvalidConfig
from wrolpi.sync import lib

@pytest.mark.parametrize('path, allowed', [
    ('videos/channel/video.mp4', True),
    ('a.txt', True),
    ('../escape.txt', False),
    ('videos/../../escape.txt', False),
    ('/etc/passwd', False),
    ('videos/.hidden/video.mp4', False),
    ('.hidden.txt', False),
    ('config/wrolpi.db', False),
    ('config/tags.yaml', False),
    ('tags/one/video.mp4', False),
    # A drive that ignores case (exFAT, NTFS, macOS) would write these into the real config and tags folders.
    ('Config/wrolpi.db', False),
    ('CONFIG/tags.yaml', False),
    ('Tags/one/video.mp4', False),
    ('videos\\video.mp4', False),
    ('', False),
])
def test_resolve_destination(test_directory, path, allowed):
    destination = lib.resolve_destination(test_directory, path)
    if allowed:
        assert destination == test_directory / path
    else:
        assert destination is None


def test_resolve_destination_refuses_symlinks(test_directory):
    """A sync never writes through a symlink; it could point outside the media directory."""
    outside = test_directory / 'outside'
    outside.mkdir()
    (test_directory / 'videos').symlink_to(outside)
    assert lib.resolve_destination(test_directory, 'videos/video.mp4') is None

    (test_directory / 'docs').mkdir()
    (test_directory / 'docs/link.txt').symlink_to(outside / 'target.txt')
    assert lib.resolve_destination(test_directory, 'docs/link.txt') is None


Primary = namedtuple('Primary', 'directory url state')


@pytest.fixture
def primary(test_directory, secondary_directory, primary_media_server) -> Primary:
    """A primary whose media is `test_directory`, served like Caddy."""
    url, state = primary_media_server(test_directory)
    return Primary(test_directory, url, state)


@pytest.mark.parametrize('values, expected', [
    ([], []),
    (['Movies'], ['Movies']),
    (['/Movies/', ' Movies ', 'Movies//'], ['Movies']),
    (['videos/Movies', 'videos'], ['videos']),
    (['Movies', 'Movies2', 'Movies/deep'], ['Movies', 'Movies2']),
    (['a//b'], ['a/b']),
    (['Movies [HD]'], ['Movies [HD]']),
])
def test_normalize_excluded_directories(values, expected):
    assert lib.normalize_excluded_directories(values) == expected


@pytest.mark.parametrize('value', ['', '/', '..', 'a/../b', '../a', 'a/./b', '.hidden', 'a/.hidden', 'config',
                                   'config/x', 'tags', 'Config', 'TAGS/x', 'a\\b', None])
def test_normalize_excluded_directories_rejects(value):
    with pytest.raises(InvalidConfig):
        lib.normalize_excluded_directories([value])


def test_is_excluded():
    assert lib.is_excluded('Movies/a.mp4', {'Movies'})
    assert lib.is_excluded('Movies', {'Movies'})
    assert not lib.is_excluded('Movies2/a.mp4', {'Movies'})
    assert not lib.is_excluded('docs/Movies/a.mp4', {'Movies'})
    assert lib.is_excluded('docs/Movies/a.mp4', {'docs/Movies'})


def test_list_local_directories(test_directory):
    for i in ('Movies', 'videos/channel', 'config', 'tags', '.hidden', 'zims', 'lost+found', 'Tags'):
        try:
            (test_directory / i).mkdir(parents=True)
        except FileExistsError:
            pass  # 'Tags' is 'tags' on a filesystem that ignores case.
    (test_directory / 'file.txt').write_text('a file')
    (test_directory / 'link').symlink_to(test_directory / 'Movies')

    assert lib.list_local_directories('') == [
        dict(name='Movies', path='Movies'), dict(name='videos', path='videos'), dict(name='zims', path='zims')]
    assert lib.list_local_directories('/videos/') == [dict(name='channel', path='videos/channel')]
    for path in ('../', 'videos/../..', 'file.txt', 'missing', 'link'):
        with pytest.raises(InvalidConfig):
            lib.list_local_directories(path)


@pytest.mark.asyncio
async def test_list_primary_directories(primary, secondary_directory, make_secondary):
    for i in ('Movies', 'videos/channel', 'config', 'tags', '.hidden', 'lost+found'):
        (primary.directory / i).mkdir(parents=True)
    (primary.directory / 'file.txt').write_text('a file')
    set_test_media_directory(secondary_directory)
    make_secondary(primary.url)

    assert await lib.list_primary_directories('') == [
        dict(name='Movies', path='Movies'), dict(name='videos', path='videos')]
    assert await lib.list_primary_directories('videos') == [dict(name='channel', path='videos/channel')]
    with pytest.raises(InvalidConfig):
        await lib.list_primary_directories('../etc')
