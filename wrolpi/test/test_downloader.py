import asyncio
import json
import pathlib
from abc import ABC
from datetime import datetime
from http import HTTPStatus
from itertools import zip_longest
from unittest import mock

import pytest
import pytz
import yaml

from wrolpi.common import get_wrolpi_config
from wrolpi.dates import Seconds
from wrolpi.db import get_db_context
from wrolpi.downloader import Downloader, Download, DownloadFrequency, import_downloads_config, \
    get_download_manager_config, RSSDownloader
from wrolpi.errors import InvalidDownload, WROLModeEnabled
from wrolpi.test.common import assert_dict_contains


@pytest.mark.asyncio
async def test_delete_old_once_downloads(test_session, test_download_manager, test_downloader):
    """Once-downloads over a month old should be deleted."""
    with mock.patch('wrolpi.downloader.now') as mock_now:
        mock_now.return_value = datetime(2020, 6, 5, 0, 0, tzinfo=pytz.UTC)

        # Recurring downloads should not be deleted.
        d1 = test_download_manager.create_download('https://example.com/1', test_downloader.name)
        d2 = test_download_manager.create_download('https://example.com/2', test_downloader.name)
        d1.frequency = 1
        d2.frequency = 1
        d2.started()
        # Should be deleted.
        d3 = test_download_manager.create_download('https://example.com/3', test_downloader.name)
        d4 = test_download_manager.create_download('https://example.com/4', test_downloader.name)
        d3.complete()
        d4.complete()
        d3.last_successful_download = datetime(2020, 1, 1, 0, 0, 0, tzinfo=pytz.UTC)
        d4.last_successful_download = datetime(2020, 5, 1, 0, 0, 0, tzinfo=pytz.UTC)
        # Not a month old.
        d5 = test_download_manager.create_download('https://example.com/5', test_downloader.name)
        d5.last_successful_download = datetime(2020, 6, 1, 0, 0, 0, tzinfo=pytz.UTC)
        # An old, but pending download should not be deleted.
        d6 = test_download_manager.create_download('https://example.com/6', test_downloader.name)
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
    test_download_manager.create_downloads(['https://example.com/1', ], test_downloader.name, settings=settings)
    download: Download = test_session.query(Download).one()
    assert download.settings == settings

    # Restarting download does not remove settings.
    test_download_manager.create_downloads(['https://example.com/1', ], test_downloader.name, settings=None)
    download: Download = test_session.query(Download).one()
    assert download.settings == settings

    # Settings can be overwritten when not None.
    test_download_manager.create_downloads(['https://example.com/1', ], test_downloader.name, settings=dict())
    download: Download = test_session.query(Download).one()
    assert download.settings == dict()


@pytest.mark.asyncio
async def test_download_rename_tag(async_client, test_session, test_download_manager, test_downloader, tag_factory):
    """Renaming a Tag renames any Downloads that reference that Tag."""
    tag = await tag_factory()

    tag_names = [tag.name, ]
    test_download_manager.create_downloads(
        ['https://example.com/1', ], test_downloader.name, tag_names=tag_names)

    download = test_session.query(Download).one()
    assert download.tag_names == ['one', ]

    await tag.update_tag('new name', tag.color, test_session)

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
    download1 = test_download_manager.create_download('https://example.com', test_downloader.name)
    assert download1.get_downloader() == test_downloader

    with pytest.raises(InvalidDownload):
        download2 = test_download_manager.create_download('https://example.com', 'bad downloader')


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
        result = test_download_manager.calculate_next_download(download)
        assert result == expected, f'{attempts} != {result}'

    d1 = Download(url='https://example.com/1', frequency=DownloadFrequency.weekly)
    d2 = Download(url='https://example.com/2', frequency=DownloadFrequency.weekly)
    d3 = Download(url='https://example.com/3', frequency=DownloadFrequency.weekly)
    test_session.add_all([d1, d2, d3])
    test_session.commit()
    # Downloads are ead out over the next week.
    assert test_download_manager.calculate_next_download(d1) == datetime(2000, 1, 8, tzinfo=pytz.UTC)
    assert test_download_manager.calculate_next_download(d2) == datetime(2000, 1, 11, 12, tzinfo=pytz.UTC)
    assert test_download_manager.calculate_next_download(d3) == datetime(2000, 1, 9, 18, tzinfo=pytz.UTC)


@pytest.mark.asyncio
async def test_recurring_downloads(test_session, test_download_manager, fake_now, test_downloader, await_switches):
    """A recurring Download should be downloaded forever."""
    test_downloader.set_test_success()

    # Download every hour.
    test_download_manager.recurring_download('https://example.com/recurring', Seconds.hour, test_downloader.name)

    # One download is scheduled.
    downloads = test_download_manager.get_new_downloads(test_session)
    assert [(i.url, i.frequency) for i in downloads] == [('https://example.com/recurring', Seconds.hour)]

    now_ = fake_now(datetime(2020, 1, 1, 0, 0, 0, tzinfo=pytz.UTC))

    # Download is processed and successful, no longer "new".
    await test_download_manager.wait_for_all_downloads()
    test_downloader.do_download.assert_called_once()
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
    test_downloader.do_download.reset_mock()
    test_downloader.set_test_failure()
    await test_download_manager.wait_for_all_downloads()
    test_downloader.do_download.assert_called_once()
    download = test_session.query(Download).one()
    # Download is deferred, last successful download remains the same.
    assert download.is_deferred, download.status_code
    assert download.last_successful_download == now_
    # Download should be retried after the DEFAULT_RETRY_FREQUENCY.
    expected = datetime(2020, 1, 1, 3, 0, 0, 997200, tzinfo=pytz.UTC)
    assert download.next_download == expected

    # Try the download again, it finally succeeds.
    test_downloader.do_download.reset_mock()
    now_ = fake_now(datetime(2020, 1, 1, 4, 0, 1, tzinfo=pytz.UTC))
    test_downloader.set_test_success()
    test_download_manager.renew_recurring_downloads()
    await test_download_manager.wait_for_all_downloads()
    test_downloader.do_download.assert_called_once()
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

    test_download_manager.create_download('https://example.com', test_downloader.name)
    await test_download_manager.wait_for_all_downloads()
    download = session.query(Download).one()
    assert download.attempts == 1

    test_download_manager.create_download('https://example.com', test_downloader.name)
    await test_download_manager.wait_for_all_downloads()
    download = session.query(Download).one()
    assert download.attempts == 2

    # There are no further attempts.
    test_downloader.set_test_unrecoverable_exception()
    test_download_manager.create_download('https://example.com', test_downloader.name)
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

    test_download_manager.create_downloads([
        'https://example.com/1',
        'https://example.com/skipme',
        'https://example.com/2',
    ], downloader_name=test_downloader.name)
    await test_download_manager.wait_for_all_downloads()
    assert_download_urls({'https://example.com/1', 'https://example.com/2'})
    assert get_download_manager_config().skip_urls == ['https://example.com/skipme']

    test_download_manager.delete_once()

    # The user can start a download even if the URL is in the skip list.
    test_download_manager.create_download('https://example.com/skipme', test_downloader.name, reset_attempts=True)
    assert_download_urls({'https://example.com/skipme'})
    assert get_download_manager_config().skip_urls == []


@pytest.mark.asyncio
async def test_process_runner_timeout(async_client, test_session, test_directory):
    """A Downloader can cancel its download using a timeout."""
    # Default timeout of 3 seconds.
    downloader = Downloader('downloader', timeout=3)

    # Sleep for 8 seconds really takes 8 seconds.
    start = datetime.now()
    await downloader.process_runner(Download(), ('sleep', '8'), test_directory, timeout=10)
    elapsed = datetime.now() - start
    assert elapsed.total_seconds() >= 8

    # Download.timeout is obeyed.
    start = datetime.now()
    await downloader.process_runner(Download(), ('sleep', '8'), test_directory)
    elapsed = datetime.now() - start
    assert 3 < elapsed.total_seconds() < 5

    # One-off timeout is obeyed.
    start = datetime.now()
    await downloader.process_runner(Download(), ('sleep', '8'), test_directory, timeout=1)
    elapsed = datetime.now() - start
    assert 1 < elapsed.total_seconds() < 3

    # Global timeout is obeyed.
    get_wrolpi_config().download_timeout = 3
    start = datetime.now()
    await downloader.process_runner(Download(), ('sleep', '8'), test_directory)
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
    script = test_directory / 'echo_script.sh'
    script.write_text(GOOD_SCRIPT)
    cmd = ('/bin/bash', script)
    result = await test_downloader.process_runner(
        Download(),
        cmd,
        test_directory,
        timeout=1
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
        timeout=1
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


@pytest.mark.asyncio
async def test_downloads_config(test_session, test_download_manager, test_download_manager_config,
                                test_downloader, assert_downloads, tag_factory, await_switches):
    # Can import with an empty config.
    await import_downloads_config()
    assert_downloads([])

    test_downloader.set_test_success()

    tag = await tag_factory()

    download1, download2 = test_download_manager.create_downloads([
        'https://example.com/1',
        'https://example.com/2',
    ], downloader_name=test_downloader.name)
    test_download_manager.recurring_download('https://example.com/3', frequency=DownloadFrequency.weekly,
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
        feed_download: Download = test_download_manager.create_download('https://example.com/feed', rss_downloader.name,
                                                                        test_session,
                                                                        sub_downloader_name=test_downloader.name,
                                                                        settings=settings)
        await test_download_manager.wait_for_all_downloads()

    downloads = list(test_download_manager.get_downloads(test_session))
    assert not feed_download.error, f'Feed download had error {feed_download.error}'
    assert len(downloads) == 3, 'Domain was not ignored'
    assert [i.url for i in downloads] == \
           ['https://example.com/feed', 'https://example.com/a', 'https://example.com/c'], f'Domain was not ignored'
