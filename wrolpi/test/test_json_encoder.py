"""Tests for the API's JSON encoder."""
import json
from pathlib import Path
from unittest import mock

import pytest

from wrolpi import api_utils
from wrolpi.api_utils import CustomJSONEncoder


def encode(obj):
    return json.loads(json.dumps(obj, cls=CustomJSONEncoder))


@pytest.mark.parametrize('path, expected', [
    ('videos/channel/video.mp4', 'videos/channel/video.mp4'),  # Inside the media directory.
    ('videos', 'videos'),
    ('', ''),  # The media directory itself.
])
def test_paths_in_media_directory_are_relative(test_directory, path, expected):
    assert encode(test_directory / path) == expected


@pytest.mark.parametrize('path', [
    'videos/video.mp4',  # Already relative.
    '/opt/wrolpi/main.py',  # Outside the media directory.
])
def test_other_paths_are_unchanged(test_directory, path):
    assert encode(Path(path)) == path


def test_relative_dot_is_empty(test_directory):
    assert encode(Path('.')) == ''


def test_sibling_of_media_directory_is_unchanged(test_directory):
    """A directory whose name merely starts with the media directory's name is not inside it."""
    sibling = Path(f'{test_directory}-sibling/video.mp4')
    assert encode(sibling) == str(sibling)


def test_media_directory_is_looked_up_once_per_response(test_directory):
    """A response can hold hundreds of paths; finding the media directory for each one was most of the
    encoding time."""
    paths = [test_directory / f'videos/{i}.mp4' for i in range(20)]
    with mock.patch.object(api_utils, 'get_media_directory', wraps=api_utils.get_media_directory) as lookup:
        assert encode(paths) == [f'videos/{i}.mp4' for i in range(20)]
    assert lookup.call_count == 1
