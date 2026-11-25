import asyncio
import gzip
import hashlib
from http import HTTPStatus
from unittest import mock

import pytest

from modules.map import climatology
from wrolpi import flags


class FakeResponse:
    def __init__(self, status, body):
        self.status, self.body = status, body

    async def read(self):
        return self.body


def fake_get(bodies):
    """aiohttp_get answering each URL from `bodies` (url -> (status, body)), keeping the URLs asked."""
    asked = []

    class Context:
        def __init__(self, url, timeout=None):
            asked.append(url)
            self.url = url

        async def __aenter__(self):
            return FakeResponse(*bodies.get(self.url, (404, b'')))

        async def __aexit__(self, *args):
            return False

    return Context, asked


@pytest.fixture
def published():
    """Months 1 and 2 published, with their sha256 pinned; the rest not yet."""
    data = {1: gzip.compress(b'WFCL one'), 2: gzip.compress(b'WFCL two')}
    months = {m: (hashlib.sha256(data[m]).hexdigest() if m in data else None) for m in range(1, 13)}
    bodies = {f'{climatology.BASE_URL}/{climatology.month_name(m)}': (200, d) for m, d in data.items()}
    with mock.patch.object(climatology, 'MONTHS', months):
        yield data, bodies


@pytest.mark.asyncio
async def test_fetch_missing(test_directory, published):
    """Each published month is fetched once, checked, and kept where the file lists do not look."""
    data, bodies = published
    get, asked = fake_get(bodies)
    with mock.patch('modules.map.climatology.aiohttp_get', get), mock.patch('modules.map.climatology.asyncio.sleep'):
        assert await climatology.fetch_missing() == [1, 2]
        assert climatology.month_path(1).read_bytes() == data[1]
        # Kept: not fetched again.
        assert await climatology.fetch_missing() == []
    assert len(asked) == 2
    assert climatology.climatology_directory().parent.name.startswith('.')
    assert climatology.status() == dict(version=climatology.VERSION, months=[1, 2],
                                        missing=list(range(3, 13)), published=False)


@pytest.mark.asyncio
async def test_fetch_month_refuses_what_is_not_expected(test_directory, published):
    data, bodies = published
    url = f'{climatology.BASE_URL}/{climatology.month_name(1)}'
    get, _ = fake_get({url: (200, b'something else')})
    with mock.patch('modules.map.climatology.aiohttp_get', get):
        with pytest.raises(climatology.ClimatologyError, match='not the file expected'):
            await climatology.fetch_month(1)
    assert climatology.month_path(1) is None

    get, _ = fake_get({url: (503, b'')})
    with mock.patch('modules.map.climatology.aiohttp_get', get):
        with pytest.raises(climatology.ClimatologyError, match='HTTP 503'):
            await climatology.fetch_month(1)
    # A month with no sha256 pinned is never fetched.
    with pytest.raises(climatology.ClimatologyError, match='No sha256'):
        await climatology.fetch_month(3)


@pytest.mark.asyncio
async def test_climatology_api(async_client, test_directory, published):
    data, bodies = published
    request, response = await async_client.get('/api/map/fallout/climatology')
    assert response.status_code == HTTPStatus.OK and response.json['months'] == []
    request, response = await async_client.get('/api/map/fallout/climatology/1')
    assert response.status_code == HTTPStatus.NOT_FOUND

    get, _ = fake_get(bodies)
    with mock.patch('modules.map.climatology.aiohttp_get', get), mock.patch('modules.map.climatology.asyncio.sleep'):
        await climatology.fetch_missing()
    request, response = await async_client.get('/api/map/fallout/climatology')
    assert response.json['months'] == [1, 2]
    request, response = await async_client.get('/api/map/fallout/climatology/2')
    assert response.status_code == HTTPStatus.OK and response.body == data[2]


@pytest.mark.asyncio
async def test_worker_waits_for_internet_and_drive(test_directory, published, flags_lock):
    """Started before the Internet and the drive are known (as on startup), the worker waits for them and then
    fetches, rather than giving up until its next hourly check."""
    flags.have_internet.clear()
    flags.media_mounted.clear()
    fetch = mock.AsyncMock(return_value=[1, 2])
    with mock.patch('modules.map.climatology.fetch_missing', fetch), \
            mock.patch('modules.map.climatology.wrol_mode_enabled', return_value=False):
        worker = asyncio.create_task(climatology.climatology_worker())
        await asyncio.sleep(0.3)
        assert not worker.done() and not fetch.called
        flags.have_internet.set()
        await asyncio.sleep(0.3)
        assert not worker.done() and not fetch.called
        flags.media_mounted.set()
        await asyncio.wait_for(worker, timeout=5)
    fetch.assert_awaited_once()


@pytest.mark.asyncio
async def test_month_kept_must_be_what_is_expected(test_directory, published):
    """A kept month that is changed, or replaced, is not listed or served, and is fetched again."""
    data, bodies = published
    get, asked = fake_get(bodies)
    with mock.patch('modules.map.climatology.aiohttp_get', get), mock.patch('modules.map.climatology.asyncio.sleep'):
        await climatology.fetch_missing()
        path = climatology.month_path(1)
        assert path

        path.write_bytes(gzip.compress(b'WFCL another month'))
        assert climatology.month_path(1) is None
        assert climatology.months_kept() == [2]

        assert await climatology.fetch_missing() == [1]
        assert climatology.month_path(1).read_bytes() == data[1]
