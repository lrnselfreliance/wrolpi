"""Tests that Channel.refresh_files() only sends Events when requested.

The Channel downloader refreshes a Channel before downloading; that refresh should not
notify the user (send_events=False), while a user-requested refresh should.
"""
import pytest

from modules.videos.models import Channel
from wrolpi.common import await_background_tasks
from wrolpi.conftest import await_file_worker


@pytest.mark.asyncio
async def test_channel_refresh_files_send_events_false(
        async_client, test_session, channel_factory, video_file_factory, events_fixture):
    """Channel.refresh_files(send_events=False) must not send refresh Events."""
    channel = channel_factory(name='MyChannel')
    video_file_factory(channel.directory / 'video.mp4')

    Channel.refresh_files(channel.id, send_events=False)
    await await_file_worker()
    await await_background_tasks()

    events_fixture.assert_no_event('directory_refresh')
    events_fixture.assert_no_event('files_refreshed')


@pytest.mark.asyncio
async def test_channel_refresh_files_send_events_default(
        async_client, test_session, channel_factory, video_file_factory, events_fixture):
    """Channel.refresh_files() sends refresh Events by default."""
    channel = channel_factory(name='MyChannel')
    video_file_factory(channel.directory / 'video.mp4')

    Channel.refresh_files(channel.id)
    await await_file_worker()
    await await_background_tasks()

    events_fixture.assert_has_event('directory_refresh')
