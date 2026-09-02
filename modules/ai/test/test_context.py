"""Tests for the library map injected into every chat."""
import time
from unittest import mock

import pytest

from modules.ai import context


@pytest.mark.asyncio
async def test_build_library_context(async_client, test_session, video_factory, archive_factory,
                                     test_zim, food_inventory_factory):
    """The map carries today's date, counts, and exact names."""
    from wrolpi.collections.models import Collection
    test_session.add(Collection(name='Talking Sasquach', kind='channel'))
    video_factory(title='a video')
    archive_factory(domain='example.com', title='a page', contents='contents')
    food_inventory_factory(name='Pantry')
    test_session.commit()

    text = context.build_library_context()
    assert 'Today is' in text
    assert '1 videos, 1 archived web pages' in text
    assert 'Talking Sasquach' in text
    assert 'example.com' in text
    assert 'WROLPi example ZIM' in text
    assert 'Pantry' in text
    assert 'user spellings may differ' in text


@pytest.mark.asyncio
async def test_library_context_caps_names(async_client, test_session, archive_factory):
    """A huge library lists at most MAX_NAMES names per category, plus a count of the rest."""
    for i in range(context.MAX_NAMES + 5):
        archive_factory(domain=f'site{i:02}.com', title=f'page {i}', contents='x')
    test_session.commit()

    text = context.build_library_context()
    assert f'Archived websites ({context.MAX_NAMES + 5}):' in text
    assert 'and 5 more' in text
    listed = [i for i in range(context.MAX_NAMES + 5) if f'site{i:02}.com' in text]
    assert len(listed) == context.MAX_NAMES


@pytest.mark.asyncio
async def test_library_context_cache_and_degradation(async_client, test_session):
    """The map is cached briefly; a build failure serves the stale copy rather than crashing chat."""
    context._cache.update(text=None, expires=0.0)
    first = context.get_library_context()
    assert first and 'Today is' in first

    with mock.patch('modules.ai.context.build_library_context', side_effect=RuntimeError('db down')) as build:
        # Cached: the builder is not called.
        assert context.get_library_context() == first
        build.assert_not_called()

        # Expired + failing builder: the stale copy is served.
        context._cache['expires'] = time.time() - 1
        assert context.get_library_context() == first
        build.assert_called_once()
