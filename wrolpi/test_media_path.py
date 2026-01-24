"""
Tests for MediaPathType to ensure paths are resolved correctly.
"""
import os
import pathlib

import pytest

from wrolpi.collections.models import Collection
from wrolpi.common import get_media_directory
from wrolpi.media_path import MediaPathType


def test_media_path_type_relative_path_resolved_against_media_directory(test_session, test_directory):
    """MediaPathType should resolve relative paths against media directory, not cwd."""
    relative_path = pathlib.Path('archive/test.com')
    collection = Collection(name='test.com', kind='domain', directory=relative_path)
    test_session.add(collection)
    test_session.commit()
    test_session.expire(collection)

    assert collection.directory.is_absolute()
    assert collection.directory == test_directory / 'archive/test.com'


def test_media_path_type_process_bind_param_relative_path(test_directory):
    """process_bind_param should resolve relative paths against media directory."""
    media_path_type = MediaPathType()
    relative_path = pathlib.Path('archive/test.com')
    result = media_path_type.process_bind_param(relative_path, dialect=None)

    assert result == str(test_directory / 'archive/test.com')
    assert not result.startswith(os.getcwd())  # NOT resolved against cwd


def test_collection_get_or_set_directory_database_roundtrip(test_session, test_directory, test_wrolpi_config):
    """get_or_set_directory should store and retrieve correct paths."""
    from unittest import mock

    collection = Collection(name='example.com', kind='domain')
    test_session.add(collection)
    test_session.commit()

    # Mock switch activation since shared context isn't set up in unit tests
    with mock.patch('modules.archive.lib.save_domains_config.activate_switch'):
        result1 = collection.get_or_set_directory(test_session)
        test_session.expire(collection)
        result2 = collection.get_or_set_directory(test_session)

    assert result1 == result2
    assert str(test_directory) in str(result2)
    assert '/opt/wrolpi' not in str(collection.directory)


def test_media_path_type_absolute_path_unchanged(test_session, test_directory):
    """Absolute paths under media directory should be stored unchanged."""
    absolute_path = test_directory / 'archive/test.com'
    collection = Collection(name='test.com', kind='domain', directory=absolute_path)
    test_session.add(collection)
    test_session.commit()
    test_session.expire(collection)

    assert collection.directory == absolute_path


def test_media_path_type_none_unchanged(test_directory):
    """None should pass through unchanged."""
    media_path_type = MediaPathType()
    result = media_path_type.process_bind_param(None, dialect=None)
    assert result is None


def test_media_path_type_empty_string_raises(test_directory):
    """Empty string should raise ValueError."""
    media_path_type = MediaPathType()
    with pytest.raises(ValueError, match='MediaPath cannot be empty'):
        media_path_type.process_bind_param('', dialect=None)


def test_media_path_type_string_path_passed_through(test_directory):
    """String paths should be passed through as-is (assumed already absolute)."""
    media_path_type = MediaPathType()
    path_str = str(test_directory / 'archive/test.com')
    result = media_path_type.process_bind_param(path_str, dialect=None)
    assert result == path_str
