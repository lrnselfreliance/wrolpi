import asyncio
from datetime import timedelta
from http import HTTPStatus
from itertools import zip_longest
from typing import List, Dict

import pytest

from wrolpi.dates import now
from wrolpi.events import Events, get_events, HISTORY_SIZE
from wrolpi.test.common import assert_dict_contains


def assert_events(expected: List[Dict], after=None):
    events = get_events(after)
    for expected, event in zip_longest(expected, events):
        assert_dict_contains(event, expected)


@pytest.mark.asyncio
async def test_events_api_feed(test_session, async_client, example_pdf, events_fixture):
    """Events can be gotten from the API."""
    # refresh_files() creates a few events.
    request, response = await async_client.post('/api/files/refresh')
    assert response.status_code == HTTPStatus.NO_CONTENT

    request, response = await async_client.get('/api/events/feed')
    assert response.status_code == HTTPStatus.OK, response.body
    assert (result := response.json.get('events'))

    # Verify using the fixture
    events_fixture.assert_has_event('global_after_refresh_completed')
    events_fixture.assert_has_event('global_refresh_indexing_completed')
    events_fixture.assert_has_event('global_refresh_modeling_completed')
    events_fixture.assert_has_event('global_refresh_discovery_completed')
    events_fixture.assert_has_event('global_refresh_started')

    # Also verify the API returns the same events
    expected = [
        dict(event='global_after_refresh_completed', subject='refresh'),
        dict(event='global_refresh_indexing_completed', subject='refresh'),
        dict(event='global_refresh_modeling_completed', subject='refresh'),
        dict(event='global_refresh_discovery_completed', subject='refresh'),
        dict(event='global_refresh_started', subject='refresh'),
    ]
    for expected, event in zip_longest(expected, result):
        assert_dict_contains(event, expected)


@pytest.mark.asyncio
async def test_events_history_limit(async_client, events_fixture):
    """EVENTS_HISTORY has a limited size."""
    for i in range(HISTORY_SIZE + 5):
        Events.send_ready()

    # Fixture provides access to events, verify size limit
    assert len(events_fixture.events) == HISTORY_SIZE


@pytest.mark.asyncio
async def test_get_events(async_client, events_fixture):
    """Test that get_events() can filter by timestamp."""
    after = now()

    Events.send_global_refresh_started()
    await asyncio.sleep(1)
    Events.send_ready()

    # Fixture shows all events
    events_fixture.assert_has_event('ready')
    events_fixture.assert_has_event('global_refresh_started')

    # get_events with after parameter filters by timestamp
    assert_events([dict(event='ready'), dict(event='global_refresh_started')], after=after)

    after = after + timedelta(seconds=0.1)
    assert_events([dict(event='ready')], after=after)
