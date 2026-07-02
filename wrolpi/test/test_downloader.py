import asyncio
import json
import pathlib
from abc import ABC
from datetime import datetime, time, timezone, timedelta
from http import HTTPStatus
from itertools import zip_longest
from unittest import mock

import pytest
import pytz
import yaml

from wrolpi.api_utils import api_app
from wrolpi.common import get_wrolpi_config, normalize_domain
from wrolpi.dates import Seconds, now
from wrolpi.db import get_db_context
from wrolpi.downloader import Downloader, Download, DownloadFrequency, import_downloads_config, \
    get_download_manager_config, RSSDownloader, parse_aria2c_progress, _parse_size, \
    set_download_progress, clear_download_progress, make_progress_callback
from wrolpi.errors import InvalidDownload, WROLModeEnabled
from wrolpi.test.common import assert_dict_contains


def test_parse_size():
    """Size strings are parsed to bytes."""
    assert _parse_size('0B') == 0
    assert _parse_size('1024B') == 1024
    assert _parse_size('1.0KiB') == 1024
    assert _parse_size('4.5MiB') == int(4.5 * 1024 ** 2)
    assert _parse_size('1.0GiB') == 1024 ** 3
    assert _parse_size('2.5TiB') == int(2.5 * 1024 ** 4)


def test_parse_aria2c_progress():
    """aria2c progress lines are parsed correctly."""
    line = '[#c52705 1.0MiB/1.0GiB(0%) CN:1 DL:4.5MiB ETA:3m44s]'
    result = parse_aria2c_progress(line)
    assert result is not None
    assert result['bytes_downloaded'] == int(1.0 * 1024 ** 2)
    assert result['total_bytes'] == 1024 ** 3
    assert result['percent'] == 0
    assert result['speed'] == int(4.5 * 1024 ** 2)
    assert result['eta'] == '3m44s'


def test_parse_aria2c_progress_no_eta():
    """aria2c progress lines without ETA are parsed."""
    line = '[#abc123 500.0MiB/1.0GiB(48%) CN:3 DL:10.0MiB]'
    result = parse_aria2c_progress(line)
    assert result is not None
    assert result['percent'] == 48
    assert result['speed'] == int(10.0 * 1024 ** 2)
    assert result['eta'] is None


def test_parse_aria2c_progress_not_progress_line():
    """Non-progress lines return None."""
    assert parse_aria2c_progress('03/12 10:00:00 [NOTICE] Download complete') is None
    assert parse_aria2c_progress('') is None
    assert parse_aria2c_progress('some random text') is None


@pytest.mark.asyncio
async def test_set_and_clear_download_progress(async_client):
    """set_download_progress stores progress in shared_ctx and clear_download_progress removes it.

    The two functions are the production wiring for ctx.report_progress / ctx.clear_progress;
    this test asserts they actually move state through shared_ctx so the API server can
    read it cross-worker.  async_client is required because shared_ctx itself only exists
    when the Sanic app is initialised.
    """
    from wrolpi.api_utils import api_app
    # No progress initially.
    data = dict(api_app.shared_ctx.download_manager_data)
    assert data.get('download_progress', {}) == {}

    # Set progress for a download.
    progress = dict(bytes_downloaded=1024, total_bytes=2048, percent=50, speed=512, eta='2s')
    set_download_progress(42, progress)
    data = dict(api_app.shared_ctx.download_manager_data)
    assert data['download_progress'][42] == progress

    # Clear it.
    clear_download_progress(42)
    data = dict(api_app.shared_ctx.download_manager_data)
    assert 42 not in data.get('download_progress', {})


def test_make_progress_callback():
    """make_progress_callback throttles and forwards parsed progress to its `report` callable.

    Pure-logic test — no Sanic, no shared_ctx.  We pass a list-append closure as `report`
    and assert what landed in it.
    """
    reported = []

    def fake_parse(line):
        if 'progress' in line:
            return dict(percent=50)
        return None

    callback = make_progress_callback(reported.append, fake_parse)

    # Non-matching line does nothing.
    callback('some other line')
    assert reported == []

    # Matching line invokes `report`.
    with mock.patch('wrolpi.downloader.time') as mock_time:
        mock_time.monotonic.return_value = 100.0
        callback('progress line')
        assert reported == [dict(percent=50)]

        # A call within 1 second is throttled.
        mock_time.monotonic.return_value = 100.5
        callback('progress line')
        assert reported == [dict(percent=50)]  # unchanged — throttle held

        # After the throttle window passes, the next matching line is reported.
        mock_time.monotonic.return_value = 102.0
        callback('progress line')
        assert reported == [dict(percent=50), dict(percent=50)]


@pytest.mark.asyncio
async def test_cancel_wrapper_outer_cancellation(test_session, test_download_manager, test_downloader):
    """cancel_wrapper propagates outer CancelledError and cancels the inner task."""
    from wrolpi.conftest import make_test_ctx
    download = test_download_manager.create_download(test_session, 'https://example.com/cancel', test_downloader.name)
    test_session.commit()

    inner_cancelled = asyncio.Event()

    async def slow_coro():
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            inner_cancelled.set()
            raise

    wrapper_task = asyncio.create_task(Downloader.cancel_wrapper(slow_coro(), download, ctx=make_test_ctx()))
    # Give the wrapper time to start polling.
    await asyncio.sleep(0.3)

    # Cancel the wrapper from outside (simulating parent cancellation).
    wrapper_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await wrapper_task

    # The inner coroutine should have been cancelled too.
    assert inner_cancelled.is_set()


@pytest.mark.asyncio
async def test_finalize_download_persists_mutations(test_session, test_download_manager, test_downloader):
    """finalize_download's mutations to the Download (e.g. sub_downloader) must persist.

    Reproduces the perpetually-pending bug: the phase-split dispatch passed a *detached* Download to
    finalize_download, so `download.sub_downloader = ...` was silently lost.  The status block then re-read
    sub_downloader=None and called create_downloads(downloader_name=None) -> InvalidDownload, which was
    swallowed, rolling back the parent's complete() and leaving it stuck `pending`."""
    from wrolpi.downloader import Downloader, DownloadResult, signal_download_download
    from wrolpi.conftest import production_like_sessions

    class FinalizeChannelLikeDownloader(Downloader, ABC):
        """Mimics ChannelDownloader: execute returns a non-DownloadResult so finalize runs, and finalize sets
        sub_downloader and returns child URLs to enqueue."""
        name = 'finalize_channel_like'

        def prepare_download(self, session, download):
            return object()  # sentinel -> phase-split (finalize) path

        async def execute_download(self, prepared, ctx, download=None):
            await asyncio.sleep(0)
            return object()  # not a DownloadResult -> finalize_download runs

        def finalize_download(self, session, download, executed):
            download.sub_downloader = test_downloader.name
            return DownloadResult(success=True, downloads=['https://example.com/child-video'])

    test_download_manager.register_downloader(FinalizeChannelLikeDownloader())
    parent = test_download_manager.create_download(test_session, 'https://example.com/channel/videos',
                                                   'finalize_channel_like')
    parent_id = parent.id
    test_session.commit()

    with production_like_sessions(test_session) as maker:
        await signal_download_download(parent_id, 'https://example.com/channel/videos')
        verify = maker()
        try:
            parent = verify.query(Download).filter_by(id=parent_id).one()
            assert parent.status == 'complete', f'parent should complete, got {parent.status}'
            assert parent.sub_downloader == test_downloader.name, 'finalize_download mutation must persist'
            child = verify.query(Download).filter_by(url='https://example.com/child-video').one()
            assert child.downloader == test_downloader.name, 'child enqueued with the persisted sub_downloader'
        finally:
            verify.close()


@pytest.mark.asyncio
async def test_child_download_failure_does_not_leave_parent_pending(test_session, test_download_manager,
                                                                    test_downloader):
    """A failure while enqueuing child downloads must not roll back / strand the successful parent.

    The parent download succeeded (it fetched the listing); enqueuing children is a separate concern.  If
    create_downloads raises (here: an unresolvable sub_downloader), the parent must still be marked complete and
    the error surfaced, not silently left `pending`."""
    from wrolpi.downloader import Downloader, DownloadResult, signal_download_download
    from wrolpi.conftest import production_like_sessions

    class BadChildDownloader(Downloader, ABC):
        name = 'bad_child'

        def prepare_download(self, session, download):
            return object()

        async def execute_download(self, prepared, ctx, download=None):
            await asyncio.sleep(0)
            return object()

        def finalize_download(self, session, download, executed):
            # Success, but no sub_downloader set -> create_downloads(downloader_name=None) will raise.
            return DownloadResult(success=True, downloads=['https://example.com/orphan-child'])

    test_download_manager.register_downloader(BadChildDownloader())
    parent = test_download_manager.create_download(test_session, 'https://example.com/bad/videos', 'bad_child')
    parent_id = parent.id
    test_session.commit()

    with production_like_sessions(test_session) as maker:
        await signal_download_download(parent_id, 'https://example.com/bad/videos')
        verify = maker()
        try:
            parent = verify.query(Download).filter_by(id=parent_id).one()
            assert parent.status == 'complete', \
                f'parent must complete despite child-enqueue failure, got {parent.status}'
            # The child could not be created, but the parent did not get stuck.
            assert verify.query(Download).filter_by(url='https://example.com/orphan-child').count() == 0
        finally:
            verify.close()


@pytest.mark.asyncio
async def test_delete_old_once_downloads(test_session, test_download_manager, test_downloader):
    """Once-downloads over a month old should be deleted."""
    with mock.patch('wrolpi.downloader.now') as mock_now:
        mock_now.return_value = datetime(2020, 6, 5, 0, 0, tzinfo=pytz.UTC)

        # Recurring downloads should not be deleted.
        d1 = test_download_manager.create_download(test_session, 'https://example.com/1', test_downloader.name)
        d2 = test_download_manager.create_download(test_session, 'https://example.com/2', test_downloader.name)
        d1.frequency = 1
        d2.frequency = 1
        d2.started()
        # Should be deleted.
        d3 = test_download_manager.create_download(test_session, 'https://example.com/3', test_downloader.name)
        d4 = test_download_manager.create_download(test_session, 'https://example.com/4', test_downloader.name)
        d3.complete()
        d4.complete()
        d3.last_successful_download = datetime(2020, 1, 1, 0, 0, 0, tzinfo=pytz.UTC)
        d4.last_successful_download = datetime(2020, 5, 1, 0, 0, 0, tzinfo=pytz.UTC)
        # Not a month old.
        d5 = test_download_manager.create_download(test_session, 'https://example.com/5', test_downloader.name)
        d5.last_successful_download = datetime(2020, 6, 1, 0, 0, 0, tzinfo=pytz.UTC)
        # An old, but pending download should not be deleted.
        d6 = test_download_manager.create_download(test_session, 'https://example.com/6', test_downloader.name)
        d6.last_successful_download = datetime(2020, 4, 1, 0, 0, 0, tzinfo=pytz.UTC)
        d6.started()

        test_download_manager.delete_old_once_downloads()

        # Two old downloads are deleted.
        downloads = test_session.query(Download).order_by(Download.id).all()
        expected = [
            dict(url='https://example.com/1', frequency=1, attempts=0, status='new'),
            dict(url='https://example.com/2', frequency=1, attempts=1, status='pending'),
            dict(url='https://example.com/5', attempts=0, status='new'),
            dict(url='https://example.com/6', attempts=1, status='pending'),
        ]
        for download, expected in zip_longest(downloads, expected):
            assert_dict_contains(download.dict(), expected)


@pytest.mark.asyncio
async def test_recreate_download(test_session, test_download_manager, test_downloader, tag_factory):
    """Settings are preserved when a Download is restarted."""
    tag = await tag_factory()
    settings = {'tag_names': [tag.name, ]}

    # Create download with settings initially.
    test_download_manager.create_downloads(test_session, ['https://example.com/1', ], test_downloader.name,
                                           settings=settings)
    download: Download = test_session.query(Download).one()
    assert download.settings == settings

    # Restarting download does not remove settings.
    test_download_manager.create_downloads(test_session, ['https://example.com/1', ], test_downloader.name,
                                           settings=None)
    download: Download = test_session.query(Download).one()
    assert download.settings == settings

    # Settings can be overwritten when not None.
    test_download_manager.create_downloads(test_session, ['https://example.com/1', ], test_downloader.name,
                                           settings=dict())
    download: Download = test_session.query(Download).one()
    assert download.settings == dict()


@pytest.mark.asyncio
async def test_download_rename_tag(async_client, test_session, test_download_manager, test_downloader, tag_factory,
                                   await_background_tasks):
    """Renaming a Tag renames any Downloads that reference that Tag."""
    tag = await tag_factory()

    tag_names = [tag.name, ]
    test_download_manager.create_downloads(
        test_session, ['https://example.com/1', ], test_downloader.name, tag_names=tag_names)

    download = test_session.query(Download).one()
    assert download.tag_names == ['one', ]

    await tag.update_tag(test_session, 'new name', tag.color)
    await await_background_tasks()  # Wait for tag rename background task

    download = test_session.query(Download).one()
    assert download.tag_names == ['new name', ]

    tag.delete()

    download = test_session.query(Download).one()
    assert download.tag_names == []


def test_downloader_must_have_name():
    """
    A Downloader class must have a name.
    """
    with pytest.raises(NotImplementedError):
        Downloader()

    class D(Downloader, ABC):
        pass

    with pytest.raises(NotImplementedError):
        D()


@mock.patch('wrolpi.common.wrol_mode_enabled', lambda: True)
@pytest.mark.asyncio
async def test_download_wrol_mode(test_session, test_download_manager):
    with pytest.raises(WROLModeEnabled):
        await test_download_manager.do_downloads()
    with pytest.raises(WROLModeEnabled):
        await test_download_manager.do_downloads()


@pytest.mark.asyncio
async def test_download_get_downloader(test_session, test_download_manager, test_downloader):
    """
    A Download can find it's Downloader.
    """
    download1 = test_download_manager.create_download(test_session, 'https://example.com', test_downloader.name)
    assert download1.get_downloader() == test_downloader

    with pytest.raises(InvalidDownload):
        download2 = test_download_manager.create_download(test_session, 'https://example.com', 'bad downloader')


@pytest.mark.asyncio
async def test_calculate_next_download(test_session, test_download_manager, fake_now):
    fake_now(datetime(2000, 1, 1))
    download = Download()
    download.frequency = DownloadFrequency.weekly
    download.status = 'deferred'

    # next_download slowly increases as we accumulate attempts.  Largest gap is the download frequency.
    attempts_expected = [
        (0, datetime(2000, 1, 1, 3, tzinfo=pytz.UTC)),
        (1, datetime(2000, 1, 1, 3, tzinfo=pytz.UTC)),
        (2, datetime(2000, 1, 1, 9, tzinfo=pytz.UTC)),
        (3, datetime(2000, 1, 2, 3, tzinfo=pytz.UTC)),
        (4, datetime(2000, 1, 4, 9, tzinfo=pytz.UTC)),
        (5, datetime(2000, 1, 8, tzinfo=pytz.UTC)),
        (6, datetime(2000, 1, 8, tzinfo=pytz.UTC)),
    ]
    for attempts, expected in attempts_expected:
        download.attempts = attempts
        result = test_download_manager.calculate_next_download(test_session, download)
        assert result == expected, f'{attempts} != {result}'

    d1 = Download(url='https://example.com/1', frequency=DownloadFrequency.weekly)
    d2 = Download(url='https://example.com/2', frequency=DownloadFrequency.weekly)
    d3 = Download(url='https://example.com/3', frequency=DownloadFrequency.weekly)
    test_session.add_all([d1, d2, d3])
    test_session.commit()
    # Downloads are ead out over the next week.
    assert test_download_manager.calculate_next_download(test_session, d1) == datetime(2000, 1, 8, tzinfo=pytz.UTC)
    assert test_download_manager.calculate_next_download(test_session, d2) == datetime(2000, 1, 11, 12, tzinfo=pytz.UTC)
    assert test_download_manager.calculate_next_download(test_session, d3) == datetime(2000, 1, 9, 18, tzinfo=pytz.UTC)


@pytest.mark.asyncio
async def test_calculate_next_download_overdue_spreading(test_session, test_download_manager, fake_now):
    """When multiple same-frequency downloads are overdue (e.g., after service restart),
    they should be spread dynamically from NOW instead of bunching up."""
    # Set up 3 weekly downloads that WERE scheduled in the past (overdue)
    d1 = Download(url='https://example.com/overdue1', frequency=DownloadFrequency.weekly)
    d1.last_successful_download = datetime(2000, 1, 1, tzinfo=pytz.UTC)  # Oldest
    d1.next_download = datetime(2000, 1, 8, tzinfo=pytz.UTC)  # Was due Jan 8

    d2 = Download(url='https://example.com/overdue2', frequency=DownloadFrequency.weekly)
    d2.last_successful_download = datetime(2000, 1, 2, tzinfo=pytz.UTC)  # Middle
    d2.next_download = datetime(2000, 1, 9, tzinfo=pytz.UTC)  # Was due Jan 9

    d3 = Download(url='https://example.com/overdue3', frequency=DownloadFrequency.weekly)
    d3.last_successful_download = datetime(2000, 1, 3, tzinfo=pytz.UTC)  # Newest
    d3.next_download = datetime(2000, 1, 10, tzinfo=pytz.UTC)  # Was due Jan 10

    test_session.add_all([d1, d2, d3])
    test_session.commit()

    # It's now Jan 15 - all three are overdue
    now_ = fake_now(datetime(2000, 1, 15, tzinfo=pytz.UTC))

    # Most overdue (d1, oldest last_successful_download) should run immediately
    assert test_download_manager.calculate_next_download(test_session, d1) == now_

    # Others spread across the week from NOW using zig_zag pattern
    # zig_zag(now, now+week) with 3 items gives: [now, now+3.5days, now+1.75days]
    d2_result = test_download_manager.calculate_next_download(test_session, d2)
    d3_result = test_download_manager.calculate_next_download(test_session, d3)

    # d2 gets second slot (middle of week), d3 gets third slot (1/4 of week)
    assert d2_result == datetime(2000, 1, 18, 12, tzinfo=pytz.UTC)  # now + 3.5 days
    assert d3_result == datetime(2000, 1, 16, 18, tzinfo=pytz.UTC)  # now + 1.75 days


@pytest.mark.asyncio
async def test_overdue_recurring_download_not_requeued_after_completion(test_session, test_download_manager, fake_now,
                                                                       test_downloader, await_switches):
    """When multiple same-frequency downloads are overdue and the most overdue one completes,
    it should NOT be immediately renewed.  Reproduces a bug where next_download was set to now()
    because calculate_next_download was called before complete(), leaving the download with stale
    pending status and last_successful_download.  This caused an infinite loop on production where
    doomandbloom.net/feed reached 3,379 attempts."""
    test_downloader.set_test_success()

    # Create 3 daily recurring downloads.
    d1 = test_download_manager.recurring_download(test_session, 'https://example.com/overdue1',
                                                  DownloadFrequency.daily, test_downloader.name)
    d2 = test_download_manager.recurring_download(test_session, 'https://example.com/overdue2',
                                                  DownloadFrequency.daily, test_downloader.name)
    d3 = test_download_manager.recurring_download(test_session, 'https://example.com/overdue3',
                                                  DownloadFrequency.daily, test_downloader.name)

    # Set them as if they were last downloaded at different times and are all overdue.
    d1.last_successful_download = datetime(2020, 1, 1, tzinfo=pytz.UTC)
    d1.next_download = datetime(2020, 1, 2, tzinfo=pytz.UTC)
    d1.status = 'complete'
    d2.last_successful_download = datetime(2020, 1, 2, tzinfo=pytz.UTC)
    d2.next_download = datetime(2020, 1, 3, tzinfo=pytz.UTC)
    d2.status = 'complete'
    d3.last_successful_download = datetime(2020, 1, 3, tzinfo=pytz.UTC)
    d3.next_download = datetime(2020, 1, 4, tzinfo=pytz.UTC)
    d3.status = 'complete'
    test_session.commit()

    # It's now Jan 10 — all three are overdue.
    fake_now(datetime(2020, 1, 10, tzinfo=pytz.UTC))

    # Renew overdue downloads and let one run.
    test_download_manager.renew_recurring_downloads()
    await test_download_manager.wait_for_all_downloads()
    test_session.expire_all()

    # At least one download should have completed.
    completed = [d for d in [d1, d2, d3] if d.is_complete]
    assert len(completed) >= 1, \
        f'Expected at least one completed download, got statuses: {[d.status for d in [d1, d2, d3]]}'

    # Advance 30 seconds — simulating the real download cycle interval.  In production, real time
    # advances between when calculate_next_download sets next_download=now() and when
    # renew_recurring_downloads checks if next_download < now().
    fake_now(datetime(2020, 1, 10, 0, 0, 30, tzinfo=pytz.UTC))

    # The completed download should NOT be renewed — its next_download should be in the future.
    test_download_manager.renew_recurring_downloads()
    test_session.expire_all()

    for d in completed:
        assert not d.is_new, \
            f'{d.url} was renewed 30 seconds after completing — infinite re-download loop!'


@pytest.mark.asyncio
async def test_calculate_next_download_single_overdue(test_session, test_download_manager, fake_now):
    """A single overdue download should use normal scheduling (not spread logic)."""
    d1 = Download(url='https://example.com/overdue', frequency=DownloadFrequency.weekly)
    d1.last_successful_download = datetime(2000, 1, 1, tzinfo=pytz.UTC)
    d1.next_download = datetime(2000, 1, 8, tzinfo=pytz.UTC)  # Was due Jan 8

    d2 = Download(url='https://example.com/not_overdue', frequency=DownloadFrequency.weekly)
    d2.last_successful_download = datetime(2000, 1, 10, tzinfo=pytz.UTC)
    d2.next_download = datetime(2000, 1, 20, tzinfo=pytz.UTC)  # Not overdue (due Jan 20)

    test_session.add_all([d1, d2])
    test_session.commit()

    # It's now Jan 15 - only d1 is overdue
    fake_now(datetime(2000, 1, 15, tzinfo=pytz.UTC))

    # Single overdue download uses normal zig_zag scheduling (next iteration boundary)
    result = test_download_manager.calculate_next_download(test_session, d1)
    # Should be in the next iteration window, not NOW
    assert result >= datetime(2000, 1, 15, tzinfo=pytz.UTC)
    assert result != datetime(2000, 1, 15, tzinfo=pytz.UTC)  # Not immediately


@pytest.mark.asyncio
async def test_calculate_next_download_new_download_while_overdue(test_session, test_download_manager, fake_now):
    """A new download added while other same-frequency downloads are overdue should run first."""
    # Existing download that is overdue
    d1 = Download(url='https://example.com/overdue', frequency=DownloadFrequency.weekly)
    d1.last_successful_download = datetime(2000, 1, 1, tzinfo=pytz.UTC)
    d1.next_download = datetime(2000, 1, 8, tzinfo=pytz.UTC)  # Was due Jan 8

    # Another overdue download
    d2 = Download(url='https://example.com/overdue2', frequency=DownloadFrequency.weekly)
    d2.last_successful_download = datetime(2000, 1, 2, tzinfo=pytz.UTC)
    d2.next_download = datetime(2000, 1, 9, tzinfo=pytz.UTC)  # Was due Jan 9

    # New download with no history
    d3 = Download(url='https://example.com/new', frequency=DownloadFrequency.weekly)
    d3.last_successful_download = None  # Never downloaded
    d3.next_download = None  # Never scheduled

    test_session.add_all([d1, d2, d3])
    test_session.commit()

    # It's now Jan 15 - d1 and d2 are overdue, d3 is new
    now_ = fake_now(datetime(2000, 1, 15, tzinfo=pytz.UTC))

    # New download (d3) should run immediately because there are overdue downloads
    assert test_download_manager.calculate_next_download(test_session, d3) == now_


@pytest.mark.asyncio
async def test_recurring_downloads(test_session, test_download_manager, fake_now, test_downloader, await_switches):
    """A recurring Download should be downloaded forever."""
    test_downloader.set_test_success()

    # Download every hour.
    test_download_manager.recurring_download(test_session, 'https://example.com/recurring', Seconds.hour,
                                             test_downloader.name)

    # One download is scheduled.
    downloads = test_download_manager.get_new_downloads(test_session)
    assert [(i.url, i.frequency) for i in downloads] == [('https://example.com/recurring', Seconds.hour)]

    now_ = fake_now(datetime(2020, 1, 1, 0, 0, 0, tzinfo=pytz.UTC))

    # Download is processed and successful, no longer "new".
    await test_download_manager.wait_for_all_downloads()
    test_downloader.execute_download.assert_called_once()
    assert list(test_download_manager.get_new_downloads(test_session)) == []
    downloads = list(test_download_manager.get_recurring_downloads(test_session))
    assert len(downloads) == 1
    download = downloads[0]
    expected = datetime(2020, 1, 1, 1, 0, 0, tzinfo=pytz.UTC)
    assert download.is_complete, download.status_code
    assert download.next_download == expected
    assert download.last_successful_download == now_

    # Download is not due for an hour.
    test_download_manager.renew_recurring_downloads()
    await test_download_manager.wait_for_all_downloads()
    assert list(test_download_manager.get_new_downloads(test_session)) == []
    assert download.last_successful_download == now_

    # Download is due an hour later.
    fake_now(datetime(2020, 1, 1, 2, 0, 1, tzinfo=pytz.UTC))
    test_download_manager.renew_recurring_downloads()
    (download,) = list(test_download_manager.get_new_downloads(test_session))
    # Download is "new" but has not been downloaded a second time.
    assert download.is_new, download.status_code
    assert download.next_download == expected
    assert download.last_successful_download == now_

    # Try the download, but it fails.
    test_downloader.execute_download.reset_mock()
    test_downloader.set_test_failure()
    await test_download_manager.wait_for_all_downloads()
    test_downloader.execute_download.assert_called_once()
    download = test_session.query(Download).one()
    # Download is deferred, last successful download remains the same.
    assert download.is_deferred, download.status_code
    assert download.last_successful_download == now_
    # Download should be retried using exponential backoff: now + min(3^attempts * hour, frequency).
    expected = datetime(2020, 1, 1, 3, 0, 1, tzinfo=pytz.UTC)
    assert download.next_download == expected

    # Try the download again, it finally succeeds.
    test_downloader.execute_download.reset_mock()
    now_ = fake_now(datetime(2020, 1, 1, 4, 0, 1, tzinfo=pytz.UTC))
    test_downloader.set_test_success()
    test_download_manager.renew_recurring_downloads()
    await test_download_manager.wait_for_all_downloads()
    test_downloader.execute_download.assert_called_once()
    download = test_session.query(Download).one()
    assert download.is_complete, download.status_code
    assert download.last_successful_download == now_
    # Floats cause slightly wrong date.
    assert download.next_download == datetime(2020, 1, 1, 5, 0, 0, 997200, tzinfo=pytz.UTC)


@pytest.mark.asyncio
async def test_max_attempts(test_session, test_download_manager, test_downloader, await_switches):
    """A Download will only be attempted so many times, it will eventually be deleted."""
    _, session = get_db_context()

    test_downloader.set_test_success()

    test_download_manager.create_download(test_session, 'https://example.com', test_downloader.name)
    await test_download_manager.wait_for_all_downloads()
    download = session.query(Download).one()
    assert download.attempts == 1

    test_download_manager.create_download(test_session, 'https://example.com', test_downloader.name)
    await test_download_manager.wait_for_all_downloads()
    download = session.query(Download).one()
    assert download.attempts == 2

    # There are no further attempts.
    test_downloader.set_test_unrecoverable_exception()
    test_download_manager.create_download(test_session, 'https://example.com', test_downloader.name)
    await test_download_manager.wait_for_all_downloads()
    download = session.query(Download).one()
    assert download.attempts == 3
    assert download.is_failed


@pytest.mark.asyncio
async def test_skip_urls(test_session, test_download_manager, assert_download_urls, test_downloader, await_switches,
                         test_download_manager_config):
    """The DownloadManager will not create downloads for URLs in its skip list."""
    _, session = get_db_context()
    get_download_manager_config().skip_urls = ['https://example.com/skipme']

    test_downloader.set_test_success()

    test_download_manager.create_downloads(test_session, [
        'https://example.com/1',
        'https://example.com/skipme',
        'https://example.com/2',
    ], downloader_name=test_downloader.name)
    await test_download_manager.wait_for_all_downloads()
    assert_download_urls({'https://example.com/1', 'https://example.com/2'})
    assert get_download_manager_config().skip_urls == ['https://example.com/skipme']

    test_download_manager.delete_once(test_session)

    # The user can start a download even if the URL is in the skip list.
    test_download_manager.create_download(test_session, 'https://example.com/skipme', test_downloader.name,
                                          reset_attempts=True, override_skip=True)
    assert_download_urls({'https://example.com/skipme'})
    assert get_download_manager_config().skip_urls == []


@pytest.mark.asyncio
async def test_skip_urls_none(test_session, test_download_manager, test_downloader, test_download_manager_config):
    """The DownloadManager does not crash when skip_urls is None in the config."""
    config = get_download_manager_config()
    config._config['skip_urls'] = None

    test_downloader.set_test_success()

    # Should not raise TypeError.
    test_download_manager.create_downloads(test_session, [
        'https://example.com/1',
    ], downloader_name=test_downloader.name)

    downloads = test_session.query(Download).all()
    assert len(downloads) == 1


@pytest.mark.asyncio
async def test_skip_already_downloaded_via_filegroup(test_session, test_download_manager, assert_download_urls,
                                                    test_downloader):
    """When skip_already_downloaded is set, URLs already present in FileGroup.url are filtered out."""
    test_downloader.set_test_success()
    # The downloader reports any URL with 'existing' in it as already downloaded.
    test_downloader.already_downloaded = lambda session, *urls: [
        type('FG', (), {'url': u})() for u in urls if 'existing' in u
    ]

    test_download_manager.create_downloads(
        test_session,
        [
            'https://example.com/new1',
            'https://example.com/existing1',
            'https://example.com/new2',
            'https://example.com/existing2',
        ],
        downloader_name=test_downloader.name,
        settings={'skip_already_downloaded': True},
    )
    assert_download_urls({'https://example.com/new1', 'https://example.com/new2'})


@pytest.mark.asyncio
async def test_skip_already_downloaded_via_completed_download(test_session, test_download_manager,
                                                             assert_download_urls, test_downloader):
    """When skip_already_downloaded is set, URLs of completed Downloads are filtered out."""
    # Pre-existing completed download.
    completed = Download(url='https://example.com/done', status='complete', downloader=test_downloader.name)
    test_session.add(completed)
    test_session.commit()

    test_downloader.set_test_success()
    test_download_manager.create_downloads(
        test_session,
        ['https://example.com/fresh', 'https://example.com/done'],
        downloader_name=test_downloader.name,
        settings={'skip_already_downloaded': True},
    )
    # The completed URL is excluded; fresh URL is queued.  The completed Download row remains.
    # Row-count + URL-set checks confirm no new row was inserted for 'done'.
    completed_id = completed.id
    assert test_session.query(Download).count() == 2
    assert_download_urls({'https://example.com/done', 'https://example.com/fresh'})
    fresh = test_session.query(Download).filter_by(url='https://example.com/fresh').one()
    assert fresh.status == 'new'
    done = test_session.query(Download).filter_by(url='https://example.com/done').one()
    # Status unchanged and id preserved — confirms the filter prevented renew().
    assert done.status == 'complete'
    assert done.id == completed_id


@pytest.mark.asyncio
async def test_skip_already_downloaded_disabled(test_session, test_download_manager, assert_download_urls,
                                               test_downloader):
    """Without skip_already_downloaded, existing URLs are still queued (renewed)."""
    completed = Download(url='https://example.com/done', status='complete', downloader=test_downloader.name)
    test_session.add(completed)
    test_session.commit()

    test_downloader.set_test_success()
    # Even though already_downloaded() returns the URL, we don't call it without the setting.
    test_downloader.already_downloaded = lambda session, *urls: [
        type('FG', (), {'url': 'https://example.com/done'})()
    ]

    test_download_manager.create_downloads(
        test_session,
        ['https://example.com/done'],
        downloader_name=test_downloader.name,
    )
    # The existing Download row is reused and renewed (status reset to new).
    assert_download_urls({'https://example.com/done'})
    download = test_session.query(Download).filter_by(url='https://example.com/done').one()
    assert download.status == 'new'


@pytest.mark.asyncio
async def test_process_runner_timeout(async_client, test_session, test_directory):
    """A Downloader can cancel its download using a timeout."""
    from wrolpi.conftest import make_test_ctx
    # Default timeout of 3 seconds.
    downloader = Downloader('downloader', timeout=3)

    # Sleep for 8 seconds really takes 8 seconds.
    start = datetime.now()
    await downloader.process_runner(Download(), ('sleep', '8'), test_directory,
                                    timeout=10, ctx=make_test_ctx())
    elapsed = datetime.now() - start
    assert elapsed.total_seconds() >= 8

    # Downloader.timeout (class default) is obeyed.
    start = datetime.now()
    await downloader.process_runner(Download(), ('sleep', '8'), test_directory, ctx=make_test_ctx())
    elapsed = datetime.now() - start
    assert 3 < elapsed.total_seconds() < 5

    # One-off timeout is obeyed.
    start = datetime.now()
    await downloader.process_runner(Download(), ('sleep', '8'), test_directory,
                                    timeout=1, ctx=make_test_ctx())
    elapsed = datetime.now() - start
    assert 1 < elapsed.total_seconds() < 3

    # ctx.download_timeout takes precedence over class/per-call timeouts.
    # Production builds ctx.download_timeout from get_wrolpi_config().download_timeout
    # (see DownloadContext.production); we bake the value directly here.
    start = datetime.now()
    await downloader.process_runner(Download(), ('sleep', '8'), test_directory,
                                    ctx=make_test_ctx(download_timeout=3))
    elapsed = datetime.now() - start
    assert 2 < elapsed.total_seconds() < 5


GOOD_SCRIPT = '''#! /usr/bin/env bash
echo "standard output"
echo "standard error" >&2
'''

BAD_SCRIPT = '''#! /usr/bin/env bash
echo "bad standard output"
echo "bad standard error" >&2
exit 123
'''


@pytest.mark.asyncio
async def test_process_runner_output(async_client, test_directory, test_downloader):
    from wrolpi.conftest import make_test_ctx
    script = test_directory / 'echo_script.sh'
    script.write_text(GOOD_SCRIPT)
    cmd = ('/bin/bash', script)
    result = await test_downloader.process_runner(
        Download(),
        cmd,
        test_directory,
        timeout=1,
        ctx=make_test_ctx(),
    )
    assert result.return_code == 0
    assert result.stdout == b'standard output\n'
    assert result.stderr == b'standard error\n'

    script.write_text(BAD_SCRIPT)
    cmd = ('/bin/bash', script)
    result = await test_downloader.process_runner(
        Download(),
        cmd,
        test_directory,
        timeout=1,
        ctx=make_test_ctx(),
    )
    assert result.return_code == 123
    assert result.stdout == b'bad standard output\n'
    assert result.stderr == b'bad standard error\n'


@pytest.mark.asyncio
async def test_crud_download(async_client, test_session, test_download_manager, test_downloader):
    """Test the ways that Downloads can be created."""
    body = dict(
        urls=['https://example.com', ],
        downloader=test_downloader.name,
        frequency=DownloadFrequency.weekly,
        settings=dict(excluded_urls='example.org,something'),
    )
    request, response = await async_client.post('/api/download', content=json.dumps(body))
    assert response.status_code == HTTPStatus.CREATED, response.body

    download: Download = test_session.query(Download).one()
    assert download.id
    assert download.url == 'https://example.com'
    assert download.downloader == test_downloader.name
    assert download.frequency == DownloadFrequency.weekly
    assert download.settings['excluded_urls'] == 'example.org,something'

    request, response = await async_client.get('/api/download')
    assert response.status_code == HTTPStatus.OK
    assert 'recurring_downloads' in response.json
    assert [i['url'] for i in response.json['recurring_downloads']] == ['https://example.com']

    request, response = await async_client.delete('/api/download/123')
    assert response.status_code == HTTPStatus.NOT_FOUND
    assert test_session.query(Download).count() == 1

    request, response = await async_client.delete(f'/api/download/{download.id}')
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert test_session.query(Download).count() == 0

    request, response = await async_client.delete(f'/api/download/{download.id}')
    assert response.status_code == HTTPStatus.NOT_FOUND
    assert test_session.query(Download).count() == 0

    # Let background tasks finish.
    await asyncio.sleep(1)


def test_download_settings_coerces_numeric_strings():
    """String values for numeric fields (from forms or legacy data) are coerced to
    proper types and bad/empty values are dropped. This is the core of the
    sleep_requests TypeError fix."""
    from wrolpi.schema import DownloadSettings, DownloadRequest

    raw = {
        'sleep_requests': '0.75',
        'depth': '3',
        'max_pages': '',
        'maximum_duration': '120',
        'video_count_limit': '0',
        'writesubtitles': False,
        'user_agent': '',
    }

    ds = DownloadSettings(**raw)
    cleaned = {k: v for k, v in ds.__dict__.items() if v not in ([], None)}

    assert cleaned['sleep_requests'] == 0.75 and isinstance(cleaned['sleep_requests'], float)
    assert cleaned['depth'] == 3 and isinstance(cleaned['depth'], int)
    assert 'max_pages' not in cleaned
    assert cleaned['video_count_limit'] == 0
    assert cleaned['writesubtitles'] is False

    # Full DownloadRequest path (what the API actually uses)
    req = DownloadRequest(urls=['https://ex.com/v'], downloader='video', settings=raw)
    assert req.settings['sleep_requests'] == 0.75
    assert isinstance(req.settings['sleep_requests'], float)
    assert 'max_pages' not in req.settings


@pytest.mark.parametrize('order', ['newest', 'oldest', None])
def test_download_settings_accepts_valid_download_order(order):
    from wrolpi.schema import DownloadSettings
    DownloadSettings(download_order=order)


def test_download_settings_rejects_deprecated_views_order():
    """'views' download order was deprecated; YouTube no longer provides view counts in listings."""
    from wrolpi.schema import DownloadSettings
    from wrolpi.errors import ValidationError
    with pytest.raises(ValidationError):
        DownloadSettings(download_order='views')


@pytest.mark.asyncio
async def test_downloads_config(test_session, test_download_manager, test_download_manager_config,
                                test_downloader, assert_downloads, tag_factory, await_switches):
    # Can import with an empty config.
    await import_downloads_config()
    assert_downloads([])

    test_downloader.set_test_success()

    tag = await tag_factory()

    download1, download2 = test_download_manager.create_downloads(test_session, [
        'https://example.com/1',
        'https://example.com/2',
    ], downloader_name=test_downloader.name)
    test_download_manager.recurring_download(test_session, 'https://example.com/3', frequency=DownloadFrequency.weekly,
                                             downloader_name=test_downloader.name)
    download2.next_download = datetime(2000, 1, 2, 0, 0, 0, tzinfo=pytz.UTC)
    download2.destination = 'some directory'
    download2.tag_names = [tag.name, ]
    # Completed once-downloads should be ignored.
    download1.last_successful_download = datetime(2000, 1, 1, 0, 0, 0, tzinfo=pytz.UTC)
    test_session.commit()

    # Allow background tasks to run.
    await await_switches()

    # Downloads were saved to config.
    assert get_download_manager_config().downloads, 'No downloads were saved'
    expected = [
        # https://example.com/1 is missing because it is completed.
        dict(
            url='https://example.com/2',
            frequency=None,
            next_download=datetime(2000, 1, 2, 0, 0, 0, tzinfo=pytz.UTC),
            downloader='test_downloader',
            destination='some directory',
            sub_downloader=None,
            tag_names=['one', ]
        ),
        dict(
            url='https://example.com/3',
            frequency=DownloadFrequency.weekly,
            downloader='test_downloader',
            settings=None,
            sub_downloader=None,
            tag_names=None,
        ),
    ]
    for download, expected in zip_longest(get_download_manager_config().downloads, expected):
        assert_dict_contains(download, expected)

    # Delete a Downloads, so we can import what was saved.
    test_session.query(Download).delete()
    test_session.commit()

    # Change the destination, remove Tags.
    with test_download_manager_config.open('rt') as fh:
        config_contents = yaml.load(fh, Loader=yaml.Loader)
        for idx, download in enumerate(config_contents['downloads']):
            if download['url'] == 'https://example.com/2':
                config_contents['downloads'][idx]['destination'] = 'a different directory'
                config_contents['downloads'][idx]['tag_names'] = None
    with test_download_manager_config.open('wt') as fh:
        yaml.dump(config_contents, fh)
    get_download_manager_config().initialize()

    # Import the saved downloads.
    await import_downloads_config()
    expected = [
        dict(
            url='https://example.com/2',
            frequency=None,
            next_download=datetime(2000, 1, 2, 0, 0, 0, tzinfo=pytz.UTC),
            downloader='test_downloader',
            # The destination was imported from the config.
            destination=pathlib.Path('a different directory'),
            sub_downloader=None,
            tag_names=None,  # Tags were removed.
        ),
        dict(
            url='https://example.com/3',
            frequency=DownloadFrequency.weekly,
            downloader='test_downloader',
            destination=None,
            settings=dict(),
            sub_downloader=None,
            tag_names=None,  # Tags were not added.
        ),
    ]
    assert_downloads(expected)

    # Import again, no duplicates.
    await import_downloads_config()
    assert_downloads(expected)


@pytest.mark.asyncio
async def test_download_excluded_urls(test_session, test_download_manager, test_downloader, await_switches):
    """Test that URLs that have been excluded are ignored by the download worker."""
    test_downloader.already_downloaded = lambda *i, **kw: []
    test_downloader.set_test_success()
    rss_downloader = RSSDownloader()
    test_download_manager.register_downloader(rss_downloader)

    with mock.patch('wrolpi.downloader.parse_feed') as mock_parse_feed:
        mock_parse_feed.return_value = dict(
            bozo=0,
            entries=[
                dict(link='https://example.com/a'),
                dict(link='https://example.org/b'),  # this should be ignored
                dict(link='https://example.com/c'),
                dict(link='https://example.gov/d'),
            ]
        )
        settings = dict(excluded_urls='example.org,example.gov')
        feed_download: Download = test_download_manager.create_download(test_session, 'https://example.com/feed',
                                                                        rss_downloader.name,
                                                                        sub_downloader_name=test_downloader.name,
                                                                        settings=settings)
        await test_download_manager.wait_for_all_downloads()

    downloads = list(test_download_manager.get_downloads(test_session))
    assert not feed_download.error, f'Feed download had error {feed_download.error}'
    assert len(downloads) == 3, 'Domain was not ignored'
    assert [i.url for i in downloads] == \
           ['https://example.com/feed', 'https://example.com/a', 'https://example.com/c'], f'Domain was not ignored'


@pytest.mark.asyncio
async def test_download_with_collection_id(test_session, test_download_manager, test_downloader):
    """Creating a Download with a collection_id should work correctly.

    This test verifies that downloads can be created and associated with collections.
    Note: The trigger update_channel_minimum_frequency is not tested here because
    pytest test DBs use Base.metadata.create_all() which doesn't run migrations.
    The trigger fix is tested by running against a real DB with migrations applied.
    """
    from wrolpi.collections import Collection

    # Create a Collection
    collection = Collection(
        name='Test Collection',
        kind='channel',
        directory='/tmp/test',
    )
    test_session.add(collection)
    test_session.flush([collection])

    # Creating a recurring download with collection_id should work
    download = test_download_manager.recurring_download(
        test_session,
        'https://example.com/test',
        DownloadFrequency.weekly,
        test_downloader.name,
        collection_id=collection.id,
    )
    test_session.commit()

    # Verify the download was created successfully
    assert download.id is not None
    assert download.collection_id == collection.id
    assert download.frequency == DownloadFrequency.weekly


@pytest.mark.asyncio
async def test_batch_delete_downloads(test_session, test_download_manager, test_downloader):
    """Test deleting specific downloads by their IDs."""
    d1 = test_download_manager.create_download(test_session, 'https://example.com/1', test_downloader.name)
    d2 = test_download_manager.create_download(test_session, 'https://example.com/2', test_downloader.name)
    d3 = test_download_manager.create_download(test_session, 'https://example.com/3', test_downloader.name)
    test_session.commit()

    # Capture IDs before deletion (objects become detached after)
    d1_id, d2_id, d3_id = d1.id, d2.id, d3.id

    # Delete only d1 and d3
    deleted_ids = test_download_manager.delete_downloads_by_ids(test_session, [d1_id, d3_id])
    assert set(deleted_ids) == {d1_id, d3_id}

    # Only d2 remains
    downloads = test_session.query(Download).all()
    assert len(downloads) == 1
    assert downloads[0].id == d2_id

    # Empty list returns empty
    deleted_ids = test_download_manager.delete_downloads_by_ids(test_session, [])
    assert deleted_ids == []

    # Non-existent IDs are silently ignored
    deleted_ids = test_download_manager.delete_downloads_by_ids(test_session, [9999, 8888])
    assert deleted_ids == []


@pytest.mark.asyncio
async def test_retry_downloads_includes_failed(test_session, test_download_manager, test_downloader):
    """Test that retry_downloads retries failed, pending, and deferred downloads."""
    d1 = test_download_manager.create_download(test_session, 'https://example.com/1', test_downloader.name)
    d2 = test_download_manager.create_download(test_session, 'https://example.com/2', test_downloader.name)
    d3 = test_download_manager.create_download(test_session, 'https://example.com/3', test_downloader.name)
    d4 = test_download_manager.create_download(test_session, 'https://example.com/4', test_downloader.name)

    # Set different statuses
    d1.fail()
    d1.attempts = 5
    d2.defer()
    d2.attempts = 3
    d3.status = 'pending'
    d3.attempts = 1
    d4.complete()  # completed download should not be retried
    test_session.commit()

    test_download_manager.retry_downloads(reset_attempts=True)

    test_session.refresh(d1)
    test_session.refresh(d2)
    test_session.refresh(d3)
    test_session.refresh(d4)

    assert d1.status == 'new'
    assert d1.attempts == 0
    assert d2.status == 'new'
    assert d2.attempts == 0
    assert d3.status == 'new'
    assert d3.attempts == 0
    assert d4.status == 'complete'  # unchanged


@pytest.mark.asyncio
async def test_batch_retry_downloads(test_session, test_download_manager, test_downloader):
    """Test retrying specific downloads by their IDs."""
    d1 = test_download_manager.create_download(test_session, 'https://example.com/1', test_downloader.name)
    d2 = test_download_manager.create_download(test_session, 'https://example.com/2', test_downloader.name)
    d3 = test_download_manager.create_download(test_session, 'https://example.com/3', test_downloader.name)

    # Set different statuses
    d1.fail()
    d1.attempts = 5
    d2.defer()
    d2.attempts = 3
    d3.complete()  # completed download should not be retried
    test_session.commit()

    # Retry d1 and d2 (not d3 since it's complete)
    count = test_download_manager.retry_downloads_by_ids(test_session, [d1.id, d2.id, d3.id])
    assert count == 2  # Only d1 and d2 were retried

    # Verify statuses and attempts were reset
    test_session.refresh(d1)
    test_session.refresh(d2)
    test_session.refresh(d3)

    assert d1.status == 'new'
    assert d1.attempts == 0
    assert d2.status == 'new'
    assert d2.attempts == 0
    assert d3.status == 'complete'  # unchanged

    # Empty list returns 0
    count = test_download_manager.retry_downloads_by_ids(test_session, [])
    assert count == 0


@pytest.mark.asyncio
async def test_batch_clear_completed(test_session, test_download_manager, test_downloader):
    """Test clearing specific completed downloads by their IDs."""
    d1 = test_download_manager.create_download(test_session, 'https://example.com/1', test_downloader.name)
    d2 = test_download_manager.create_download(test_session, 'https://example.com/2', test_downloader.name)
    d3 = test_download_manager.create_download(test_session, 'https://example.com/3', test_downloader.name)
    d4 = test_download_manager.create_download(test_session, 'https://example.com/4', test_downloader.name)

    # Set different statuses
    d1.complete()
    d2.complete()
    d3.fail()  # failed download should not be cleared by this method
    # d4 stays as 'new'
    test_session.commit()

    # Capture IDs before deletion (objects become detached after)
    d1_id, d2_id, d3_id, d4_id = d1.id, d2.id, d3.id, d4.id

    # Clear only d1 (which is complete)
    deleted_ids = test_download_manager.clear_completed_by_ids(test_session, [d1_id, d3_id, d4_id])
    assert deleted_ids == [d1_id]  # Only d1 was cleared (complete)

    # d2, d3, d4 remain
    downloads = test_session.query(Download).all()
    assert len(downloads) == 3
    assert {d.id for d in downloads} == {d2_id, d3_id, d4_id}

    # Empty list returns empty
    deleted_ids = test_download_manager.clear_completed_by_ids(test_session, [])
    assert deleted_ids == []


@pytest.mark.asyncio
async def test_batch_api_endpoints(async_client, test_session, test_download_manager, test_downloader):
    """Test the batch API endpoints."""
    d1 = test_download_manager.create_download(test_session, 'https://example.com/1', test_downloader.name)
    d2 = test_download_manager.create_download(test_session, 'https://example.com/2', test_downloader.name)
    d3 = test_download_manager.create_download(test_session, 'https://example.com/3', test_downloader.name)
    d1.fail()
    d2.complete()
    test_session.commit()

    # Capture IDs before operations (objects become detached after deletion)
    d1_id, d2_id, d3_id = d1.id, d2.id, d3.id

    # Test batch retry endpoint
    body = dict(download_ids=[d1_id])
    request, response = await async_client.post('/api/download/batch/retry', content=json.dumps(body))
    assert response.status_code == HTTPStatus.OK
    assert response.json['retried_count'] == 1
    test_session.refresh(d1)
    # Status may be 'new', 'pending', or 'complete' depending on whether the download worker
    # picked it up and completed before the assertion is checked.
    assert d1.status in ('new', 'pending', 'complete')

    # Test batch clear endpoint
    body = dict(download_ids=[d2_id])
    request, response = await async_client.post('/api/download/batch/clear', content=json.dumps(body))
    assert response.status_code == HTTPStatus.OK
    assert response.json['deleted_ids'] == [d2_id]
    assert test_session.query(Download).filter_by(id=d2_id).count() == 0

    # Test batch delete endpoint
    body = dict(download_ids=[d1_id, d3_id])
    request, response = await async_client.post('/api/download/batch/delete', content=json.dumps(body))
    assert response.status_code == HTTPStatus.OK
    assert set(response.json['deleted_ids']) == {d1_id, d3_id}
    assert test_session.query(Download).count() == 0

    # Test validation - empty list should fail
    body = dict(download_ids=[])
    request, response = await async_client.post('/api/download/batch/delete', content=json.dumps(body))
    assert response.status_code == HTTPStatus.BAD_REQUEST


@pytest.mark.asyncio
async def test_child_downloads_have_parent_download_url(test_session, test_download_manager, test_downloader):
    """Child downloads spawned by a parent download should have parent_download_url set in their settings."""
    import asyncio
    from wrolpi.downloader import DownloadResult

    parent_url = 'https://example.com/parent'
    child_urls = ['https://example.com/child1', 'https://example.com/child2']

    # Track which URLs have been processed to avoid returning children for child downloads
    processed_urls = set()

    # Configure the test_downloader to return child downloads only for the parent URL.
    # New signature matches Downloader.execute_download(prepared, ctx, download=...).
    async def download_with_children(prepared, ctx, *, download=None, **kwargs):
        await asyncio.sleep(0.1)
        if download is not None and download.url == parent_url and parent_url not in processed_urls:
            processed_urls.add(parent_url)
            return DownloadResult(success=True, downloads=child_urls)
        # Return success without children for child downloads
        return DownloadResult(success=True)

    test_downloader.execute_download.side_effect = download_with_children

    # Create the parent download with a sub_downloader specified
    test_download_manager.create_download(test_session, parent_url, test_downloader.name,
                                          sub_downloader_name=test_downloader.name)
    test_session.commit()

    # Wait for the parent download to complete and create child downloads
    await test_download_manager.wait_for_all_downloads()

    # Get all downloads
    downloads = test_session.query(Download).all()
    assert len(downloads) == 3, f'Expected 3 downloads (1 parent + 2 children), got {len(downloads)}'

    # Find parent and child downloads
    parent_download = next((d for d in downloads if d.url == parent_url), None)
    child_downloads = [d for d in downloads if d.url in child_urls]

    assert parent_download is not None, 'Parent download not found'
    assert len(child_downloads) == 2, f'Expected 2 child downloads, got {len(child_downloads)}'

    # Verify child downloads have parent_download_url in their settings
    for child in child_downloads:
        assert child.settings is not None, f'Child download {child.url} has no settings'
        assert 'parent_download_url' in child.settings, f'Child download {child.url} missing parent_download_url'
        assert child.settings['parent_download_url'] == parent_url, \
            f'Child download {child.url} has wrong parent_download_url: {child.settings.get("parent_download_url")}'


def test_yaml_dump_filters_default_settings(test_session, test_download_manager, test_download_manager_config,
                                            test_downloader):
    """Settings matching global defaults should be stripped from YAML."""
    from modules.videos.lib import set_test_downloader_config, get_videos_downloader_config

    set_test_downloader_config(True)
    try:
        config = get_videos_downloader_config()

        # Create a download with settings that match global defaults
        download = test_download_manager.create_download(
            test_session, 'https://example.com/channel', test_downloader.name,
            settings={
                'video_resolutions': config.video_resolutions,
                'video_format': config.merge_output_format,
                'writesubtitles': config.writesubtitles,
                'title_include': 'important',  # non-inheritable, should be kept
            },
        )
        download.frequency = 99
        test_session.commit()

        get_download_manager_config().dump_config()

        # Read the YAML and check
        yaml_data = get_download_manager_config()._config
        download_entry = next(d for d in yaml_data['downloads'] if d['url'] == 'https://example.com/channel')

        # Inheritable defaults should be filtered out
        settings = download_entry['settings']
        assert 'video_resolutions' not in settings, 'Default video_resolutions should be filtered from YAML'
        assert 'video_format' not in settings, 'Default video_format should be filtered from YAML'
        assert 'writesubtitles' not in settings, 'Default writesubtitles should be filtered from YAML'
        # Non-inheritable settings should be preserved
        assert settings['title_include'] == 'important', 'Non-inheritable settings should be kept in YAML'
    finally:
        set_test_downloader_config(False)


def test_yaml_dump_keeps_overrides(test_session, test_download_manager, test_download_manager_config,
                                   test_downloader):
    """Settings that differ from global defaults should be kept in YAML."""
    from modules.videos.lib import set_test_downloader_config

    set_test_downloader_config(True)
    try:
        # Create a download with settings that differ from global defaults
        download = test_download_manager.create_download(
            test_session, 'https://example.com/channel2', test_downloader.name,
            settings={
                'video_resolutions': ['720p'],  # differs from default
                'writesubtitles': False,  # differs from default True
            },
        )
        download.frequency = 99
        test_session.commit()

        get_download_manager_config().dump_config()

        yaml_data = get_download_manager_config()._config
        download_entry = next(d for d in yaml_data['downloads'] if d['url'] == 'https://example.com/channel2')
        settings = download_entry['settings']

        assert settings['video_resolutions'] == ['720p'], 'Non-default video_resolutions should be kept'
        assert settings['writesubtitles'] is False, 'Non-default writesubtitles should be kept'
    finally:
        set_test_downloader_config(False)


def test_is_within_download_window_no_config(test_download_manager):
    """Returns True when no download window is configured."""
    config = get_wrolpi_config()
    config.download_window_start = None
    config.download_window_end = None
    assert test_download_manager.is_within_download_window() is True

    # Only one field set should also return True (no restriction).
    config.download_window_start = '08:00'
    config.download_window_end = None
    assert test_download_manager.is_within_download_window() is True

    config.download_window_start = None
    config.download_window_end = '17:00'
    assert test_download_manager.is_within_download_window() is True


def test_is_within_download_window_same_day(test_download_manager):
    """Same-day window (e.g. 08:00-17:00) boundary checks."""
    config = get_wrolpi_config()
    config.download_window_start = '08:00'
    config.download_window_end = '17:00'

    # Before window
    with mock.patch.object(type(test_download_manager), '_get_local_time', return_value=time(7, 59)):
        assert test_download_manager.is_within_download_window() is False

    # Start of window
    with mock.patch.object(type(test_download_manager), '_get_local_time', return_value=time(8, 0)):
        assert test_download_manager.is_within_download_window() is True

    # Middle of window
    with mock.patch.object(type(test_download_manager), '_get_local_time', return_value=time(12, 0)):
        assert test_download_manager.is_within_download_window() is True

    # End of window (exclusive)
    with mock.patch.object(type(test_download_manager), '_get_local_time', return_value=time(17, 0)):
        assert test_download_manager.is_within_download_window() is False

    # After window
    with mock.patch.object(type(test_download_manager), '_get_local_time', return_value=time(23, 0)):
        assert test_download_manager.is_within_download_window() is False


def test_is_within_download_window_overnight(test_download_manager):
    """Overnight window (e.g. 22:00-06:00) wrapping."""
    config = get_wrolpi_config()
    config.download_window_start = '22:00'
    config.download_window_end = '06:00'

    # Before window (daytime)
    with mock.patch.object(type(test_download_manager), '_get_local_time', return_value=time(12, 0)):
        assert test_download_manager.is_within_download_window() is False

    # Just before window start
    with mock.patch.object(type(test_download_manager), '_get_local_time', return_value=time(21, 59)):
        assert test_download_manager.is_within_download_window() is False

    # Start of window
    with mock.patch.object(type(test_download_manager), '_get_local_time', return_value=time(22, 0)):
        assert test_download_manager.is_within_download_window() is True

    # Middle of night
    with mock.patch.object(type(test_download_manager), '_get_local_time', return_value=time(3, 0)):
        assert test_download_manager.is_within_download_window() is True

    # End of window (exclusive)
    with mock.patch.object(type(test_download_manager), '_get_local_time', return_value=time(6, 0)):
        assert test_download_manager.is_within_download_window() is False


def test_download_window_renews_download(test_session, test_download_manager, test_downloader):
    """A download stopped by the window closing is renewed to 'new' status."""
    from wrolpi.downloader import DownloadResult
    download = test_download_manager.create_download(test_session, 'https://example.com/window', test_downloader.name)
    download.started()
    test_session.commit()

    # Simulate the result that cancel_wrapper returns when outside the window.
    result = DownloadResult(success=False, error='Download paused: outside download window')

    # Apply the same logic as signal_download_download.
    download.location = result.location or download.location or None
    download.error = result.error if result.error else None

    if result.error and 'outside download window' in result.error:
        download.renew()
        download.error = result.error

    test_session.commit()
    test_session.refresh(download)

    assert download.status == 'new'
    assert 'outside download window' in download.error


def test_download_window_yaml_sexagesimal():
    """YAML parses some HH:MM values as sexagesimal integers.  The config normalizes them back to strings."""
    from wrolpi.common import WROLPiConfig
    assert WROLPiConfig._normalize_time_value(None) is None
    assert WROLPiConfig._normalize_time_value('07:00') == '07:00'
    assert WROLPiConfig._normalize_time_value('21:00') == '21:00'
    # YAML parses 21:00 as 1260 (sexagesimal)
    assert WROLPiConfig._normalize_time_value(1260) == '21:00'
    # YAML parses 17:00 as 1020
    assert WROLPiConfig._normalize_time_value(1020) == '17:00'
    # YAML parses 22:30 as 1350
    assert WROLPiConfig._normalize_time_value(1350) == '22:30'


def test_is_within_download_window_uses_local_time(test_download_manager):
    """Download window should compare against local time, not UTC.

    Bug: now() returns UTC. At 1:00 AM MDT (UTC-6), UTC is 07:00.
    With a window of 07:00-20:00, the old code incorrectly returned True
    because it compared UTC 07:00 against the window. The local time is
    01:00, which is outside the window.
    """
    config = get_wrolpi_config()
    config.download_window_start = '07:00'
    config.download_window_end = '20:00'

    # Simulate local time of 01:00 AM (outside the 07:00-20:00 window).
    with mock.patch.object(type(test_download_manager), '_get_local_time',
                           return_value=time(1, 0)):
        assert test_download_manager.is_within_download_window() is False

    # Simulate local time of 12:00 PM (inside the window).
    with mock.patch.object(type(test_download_manager), '_get_local_time',
                           return_value=time(12, 0)):
        assert test_download_manager.is_within_download_window() is True


def test_get_local_time_with_configured_timezone(test_download_manager):
    """When config.timezone is set, _get_local_time() converts to that timezone."""

    config = get_wrolpi_config()
    config.timezone = 'America/Denver'

    # Mock now() to return a known UTC time: 2024-01-15 18:00:00 UTC
    # Denver is UTC-7 in January (MST), so local time should be 11:00:00.
    mock_utc = datetime(2024, 1, 15, 18, 0, 0, tzinfo=timezone.utc)
    with mock.patch('wrolpi.downloader.now', return_value=mock_utc):
        result = test_download_manager._get_local_time()
    assert result == time(11, 0, 0)

    # Summer time: 2024-07-15 18:00:00 UTC
    # Denver is UTC-6 in July (MDT), so local time should be 12:00:00.
    mock_utc_summer = datetime(2024, 7, 15, 18, 0, 0, tzinfo=timezone.utc)
    with mock.patch('wrolpi.downloader.now', return_value=mock_utc_summer):
        result = test_download_manager._get_local_time()
    assert result == time(12, 0, 0)


def test_get_local_time_without_configured_timezone(test_download_manager):
    """When config.timezone is None, _get_local_time() falls back to system timezone."""
    config = get_wrolpi_config()
    config.timezone = None

    mock_utc = datetime(2024, 1, 15, 18, 0, 0, tzinfo=timezone.utc)
    with mock.patch('wrolpi.downloader.now', return_value=mock_utc):
        result = test_download_manager._get_local_time()
    # Should return the system's local time conversion.
    expected = mock_utc.astimezone().time()
    assert result == expected


def test_require_media_mounted_config_default(test_download_manager, test_wrolpi_config):
    """require_media_mounted defaults to True (safe default for fresh installs)."""
    assert get_wrolpi_config().require_media_mounted is True


def test_require_media_mounted_gate_blocks_when_flag_clear(test_download_manager, test_wrolpi_config, flags_lock):
    """can_download returns False when the gate is on and the media_mounted flag is clear.

    Bypasses the PYTEST short-circuit at the top of can_download so the gate logic runs.
    """
    from wrolpi import flags
    config = get_wrolpi_config()
    config.require_media_mounted = True
    flags.media_mounted.clear()
    flags.have_internet.set()  # other gates must pass

    with mock.patch('wrolpi.downloader.PYTEST', False), \
            mock.patch('wrolpi.downloader.wrol_mode_enabled', return_value=False):
        assert test_download_manager.can_download is False


def test_require_media_mounted_gate_allows_when_flag_set(test_download_manager, test_wrolpi_config, flags_lock):
    """The gate stops blocking once media_mounted is set."""
    from wrolpi import flags
    config = get_wrolpi_config()
    config.require_media_mounted = True
    flags.media_mounted.set()
    flags.have_internet.set()
    # Make successful_import True so the function reaches the final return True.
    get_download_manager_config().successful_import = True

    with mock.patch('wrolpi.downloader.PYTEST', False), \
            mock.patch('wrolpi.downloader.wrol_mode_enabled', return_value=False):
        assert test_download_manager.can_download is True


def test_require_media_mounted_gate_opt_out(test_download_manager, test_wrolpi_config, flags_lock):
    """When the user opts out via the config, the gate is skipped even with the flag clear."""
    from wrolpi import flags
    config = get_wrolpi_config()
    config.require_media_mounted = False
    flags.media_mounted.clear()
    flags.have_internet.set()
    get_download_manager_config().successful_import = True

    with mock.patch('wrolpi.downloader.PYTEST', False), \
            mock.patch('wrolpi.downloader.wrol_mode_enabled', return_value=False):
        assert test_download_manager.can_download is True


# ===================================================================================================
# Daily download limits (per-domain and global)
# ===================================================================================================

def test_normalize_domain_helper():
    """The generic domain normalizer strips port, www, and other common subdomains."""
    assert normalize_domain('https://www.example.com/foo') == 'example.com'
    assert normalize_domain('https://m.example.com/foo') == 'example.com'
    assert normalize_domain('https://mobile.example.com/foo') == 'example.com'
    assert normalize_domain('https://example.com:443/foo') == 'example.com'
    assert normalize_domain('https://example.com/foo') == 'example.com'


def test_base_downloader_normalize_domain(test_downloader):
    """The base Downloader.normalize_domain strips common subdomains."""
    assert test_downloader.normalize_domain('https://m.rumble.com/abc') == 'rumble.com'
    assert test_downloader.normalize_domain('https://www.rumble.com/abc') == 'rumble.com'


def test_video_downloader_normalize_domain():
    """VideoDownloader/ChannelDownloader collapse youtu.be, shorts, and tracking params to youtube.com."""
    from modules.videos.downloader import VideoDownloader, ChannelDownloader
    # Build instances without __init__ to avoid re-registering with the global manager.
    vd = object.__new__(VideoDownloader)
    cd = object.__new__(ChannelDownloader)
    for downloader in (vd, cd):
        assert downloader.normalize_domain('https://youtu.be/abc12345') == 'youtube.com'
        assert downloader.normalize_domain('https://www.youtube.com/shorts/abc12345') == 'youtube.com'
        assert downloader.normalize_domain('https://m.youtube.com/watch?v=abc12345') == 'youtube.com'
        assert downloader.normalize_domain(
            'https://www.youtube.com/watch?v=abc12345&list=PL123&si=foo') == 'youtube.com'


def _make_processed_download(session, downloader_name, url, *, when=None, frequency=None, status='complete'):
    """Create a Download that looks like it was already attempted (for daily-limit counting)."""
    download = Download(url=url, downloader=downloader_name, frequency=frequency, status=status)
    download.last_download_attempt = when if when is not None else now()
    session.add(download)
    session.flush()
    return download


def _dispatched_urls(dispatch_mock) -> set:
    return {c.kwargs['context']['download_url'] for c in dispatch_mock.call_args_list}


@pytest.mark.asyncio
async def test_daily_download_counts(test_session, test_download_manager, test_downloader):
    """daily_download_counts tallies non-recurring downloads attempted since local midnight, by domain."""
    name = test_downloader.name
    # Counted today: two example.com (one via m. subdomain), one rumble.com.
    _make_processed_download(test_session, name, 'https://example.com/1')
    _make_processed_download(test_session, name, 'https://m.example.com/2')
    _make_processed_download(test_session, name, 'https://rumble.com/3')
    # Not counted: recurring (has frequency), and one attempted two days ago.
    _make_processed_download(test_session, name, 'https://example.com/recurring',
                             frequency=DownloadFrequency.daily)
    _make_processed_download(test_session, name, 'https://example.com/yesterday',
                             when=now() - timedelta(days=2))
    test_session.commit()

    global_count, domain_counts = test_download_manager.daily_download_counts(test_session)
    assert global_count == 3
    assert domain_counts == {'example.com': 2, 'rumble.com': 1}


@pytest.mark.asyncio
async def test_daily_limit_per_domain_blocks(test_session, test_download_manager, test_downloader):
    """A new download is not dispatched once its domain hits the per-domain daily limit."""
    config = get_wrolpi_config()
    config.download_daily_limit_per_domain = 3
    name = test_downloader.name
    for i in range(3):
        _make_processed_download(test_session, name, f'https://example.com/done{i}')
    # A different domain under its own limit must still be allowed.
    new_blocked = Download(url='https://example.com/new', downloader=name, status='new')
    new_allowed = Download(url='https://rumble.com/new', downloader=name, status='new')
    test_session.add_all([new_blocked, new_allowed])
    test_session.commit()

    with mock.patch.object(type(api_app), 'dispatch', new_callable=mock.AsyncMock) as dispatch:
        await test_download_manager.dispatch_downloads()

    dispatched = _dispatched_urls(dispatch)
    assert 'https://example.com/new' not in dispatched
    assert 'https://rumble.com/new' in dispatched
    test_session.refresh(new_blocked)
    assert new_blocked.last_download_attempt is None
    assert new_blocked.status == 'new'


@pytest.mark.asyncio
async def test_daily_limit_per_domain_allows_under_limit(test_session, test_download_manager, test_downloader):
    """A new download is dispatched while its domain is under the per-domain daily limit."""
    config = get_wrolpi_config()
    config.download_daily_limit_per_domain = 3
    name = test_downloader.name
    for i in range(2):
        _make_processed_download(test_session, name, f'https://example.com/done{i}')
    new = Download(url='https://example.com/new', downloader=name, status='new')
    test_session.add(new)
    test_session.commit()

    with mock.patch.object(type(api_app), 'dispatch', new_callable=mock.AsyncMock) as dispatch:
        await test_download_manager.dispatch_downloads()

    assert 'https://example.com/new' in _dispatched_urls(dispatch)
    test_session.refresh(new)
    assert new.last_download_attempt is not None


@pytest.mark.asyncio
async def test_daily_limit_resets_next_day(test_session, test_download_manager, test_downloader):
    """Downloads attempted on a previous day do not count against today's limit."""
    config = get_wrolpi_config()
    config.download_daily_limit_per_domain = 3
    name = test_downloader.name
    # Three were processed two days ago; they should not count today.
    for i in range(3):
        _make_processed_download(test_session, name, f'https://example.com/old{i}',
                                 when=now() - timedelta(days=2))
    new = Download(url='https://example.com/new', downloader=name, status='new')
    test_session.add(new)
    test_session.commit()

    with mock.patch.object(type(api_app), 'dispatch', new_callable=mock.AsyncMock) as dispatch:
        await test_download_manager.dispatch_downloads()

    assert 'https://example.com/new' in _dispatched_urls(dispatch)


@pytest.mark.asyncio
async def test_daily_limit_counts_failed_attempts(test_session, test_download_manager, test_downloader):
    """A failed/deferred download attempted today still consumes a daily slot."""
    config = get_wrolpi_config()
    config.download_daily_limit_per_domain = 2
    name = test_downloader.name
    # One complete, one deferred (failed) today => 2 attempts, domain is at its limit.
    _make_processed_download(test_session, name, 'https://example.com/ok', status='complete')
    _make_processed_download(test_session, name, 'https://example.com/failed', status='deferred')
    new = Download(url='https://example.com/new', downloader=name, status='new')
    test_session.add(new)
    test_session.commit()

    with mock.patch.object(type(api_app), 'dispatch', new_callable=mock.AsyncMock) as dispatch:
        await test_download_manager.dispatch_downloads()

    assert 'https://example.com/new' not in _dispatched_urls(dispatch)


@pytest.mark.asyncio
async def test_daily_limit_global_blocks(test_session, test_download_manager, test_downloader):
    """The global daily limit caps downloads across all domains."""
    config = get_wrolpi_config()
    config.download_daily_limit_global = 3
    name = test_downloader.name
    # 3 processed today across domains (global limit reached).
    _make_processed_download(test_session, name, 'https://example.com/1')
    _make_processed_download(test_session, name, 'https://example.com/2')
    _make_processed_download(test_session, name, 'https://rumble.com/3')
    # A brand-new domain with no prior downloads is still blocked by the global cap.
    new = Download(url='https://wikipedia.org/new', downloader=name, status='new')
    test_session.add(new)
    test_session.commit()

    with mock.patch.object(type(api_app), 'dispatch', new_callable=mock.AsyncMock) as dispatch:
        await test_download_manager.dispatch_downloads()

    assert _dispatched_urls(dispatch) == set()
    test_session.refresh(new)
    assert new.last_download_attempt is None


@pytest.mark.asyncio
async def test_daily_limit_global_allows_under_limit(test_session, test_download_manager, test_downloader):
    """Downloads dispatch while the global daily total is under the limit."""
    config = get_wrolpi_config()
    config.download_daily_limit_global = 5
    name = test_downloader.name
    for i in range(3):
        _make_processed_download(test_session, name, f'https://example.com/{i}')
    new = Download(url='https://wikipedia.org/new', downloader=name, status='new')
    test_session.add(new)
    test_session.commit()

    with mock.patch.object(type(api_app), 'dispatch', new_callable=mock.AsyncMock) as dispatch:
        await test_download_manager.dispatch_downloads()

    assert 'https://wikipedia.org/new' in _dispatched_urls(dispatch)


@pytest.mark.asyncio
async def test_recurring_downloads_bypass_daily_limits(test_session, test_download_manager, test_downloader):
    """Recurring (Channel/RSS) downloads are never gated and never consume a daily slot."""
    config = get_wrolpi_config()
    # Both limits would otherwise block everything past the first download.
    config.download_daily_limit_global = 2
    config.download_daily_limit_per_domain = 2
    name = test_downloader.name
    # One non-recurring already processed today (global count = 1).
    _make_processed_download(test_session, name, 'https://example.com/done')
    # A recurring download on a different domain, and a new non-recurring download.
    recurring = Download(url='https://rumble.com/channel', downloader=name, status='new',
                         frequency=DownloadFrequency.daily)
    non_recurring = Download(url='https://example.com/new', downloader=name, status='new')
    test_session.add_all([recurring, non_recurring])
    test_session.commit()

    with mock.patch.object(type(api_app), 'dispatch', new_callable=mock.AsyncMock) as dispatch:
        await test_download_manager.dispatch_downloads()

    dispatched = _dispatched_urls(dispatch)
    # Recurring is dispatched despite the limits.  The non-recurring is also dispatched, which proves the
    # recurring download did not consume a global slot (else the global count would have reached 2 first).
    assert 'https://rumble.com/channel' in dispatched
    assert 'https://example.com/new' in dispatched

    # Recurring downloads are excluded from the daily count entirely.
    global_count, domain_counts = test_download_manager.daily_download_counts(test_session)
    assert 'rumble.com' not in domain_counts
