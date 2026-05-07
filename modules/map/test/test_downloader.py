"""Phase-split tests for MapCatalogDownloader / MapExtractDownloader / MapSearchIndexDownloader.

These exercise prepare_download and finalize_download in isolation — no async_client,
no test_download_manager, no real subprocess.  Execute paths that drive download_file +
GPG verification + filesystem rename are integration territory and are deliberately
omitted; the parent download_file ctx threading is already covered by the FileDownloader
migration tests.
"""
from unittest import mock

import pytest

from modules.archive.conftest import make_test_ctx
from modules.map.downloader import (
    ExecutedMapCatalog,
    ExecutedMapExtract,
    ExecutedMapSearchIndex,
    PreparedMapCatalog,
    PreparedMapExtract,
    PreparedMapSearchIndex,
    map_catalog_downloader,
    map_extract_downloader,
    map_search_index_downloader,
)
from wrolpi.downloader import Download


# ---------------------------------------------------------------------------
# MapCatalogDownloader
# ---------------------------------------------------------------------------


def test_catalog_prepare_extracts_subscribed_regions(test_session):
    """prepare_download surfaces the user's region subscriptions."""
    download = Download(
        url='https://maps.example.com/manifest.json',
        downloader='map_catalog',
        settings={'regions': [{'region': 'us'}, {'region': 'eu'}]},
    )

    prepared = map_catalog_downloader.prepare_download(test_session, download)

    assert isinstance(prepared, PreparedMapCatalog)
    assert prepared.url == download.url
    assert prepared.subscribed_regions == [{'region': 'us'}, {'region': 'eu'}]


def test_catalog_prepare_handles_no_regions_in_settings(test_session):
    """No 'regions' key → empty list (handled in finalize as success no-op)."""
    download = Download(
        url='https://maps.example.com/manifest.json',
        downloader='map_catalog',
        settings={},
    )

    prepared = map_catalog_downloader.prepare_download(test_session, download)

    assert prepared.subscribed_regions == []


@pytest.mark.asyncio
async def test_catalog_execute_handles_fetch_failure(test_session):
    """A fetch_manifest exception ends up on executed.error rather than raising."""

    async def fake_fetch(url):
        raise RuntimeError('CDN down')

    prepared = PreparedMapCatalog(url='https://x', subscribed_regions=[{'region': 'us'}])

    with mock.patch('modules.map.lib.fetch_manifest', fake_fetch):
        executed = await map_catalog_downloader.execute_download(prepared, make_test_ctx())

    assert executed.manifest is None
    assert 'CDN down' in (executed.error or '')


def test_catalog_finalize_no_subscribed_regions_returns_success(test_session):
    """User has no subscriptions → success no-op (skips DB writes)."""
    download = Download(url='https://x', downloader='map_catalog')
    executed = ExecutedMapCatalog(
        manifest={'regions': {'us': 'https://x/us.pmtiles'}, 'version': '2024-01'},
        subscribed_regions=[],
    )

    result = map_catalog_downloader.finalize_download(test_session, download, executed)

    assert result.success is True


def test_catalog_finalize_no_manifest_regions_returns_failure(test_session):
    """Manifest came back without a regions block → failure."""
    download = Download(url='https://x', downloader='map_catalog')
    executed = ExecutedMapCatalog(
        manifest={'regions': {}, 'version': '2024-01'},
        subscribed_regions=[{'region': 'us'}],
    )

    result = map_catalog_downloader.finalize_download(test_session, download, executed)

    assert result.success is False
    assert 'does not contain regions' in (result.error or '')


def test_catalog_finalize_propagates_executed_error(test_session):
    """An error raised during execute_download flows into the DownloadResult."""
    download = Download(url='https://x', downloader='map_catalog')
    executed = ExecutedMapCatalog(
        manifest=None, subscribed_regions=[{'region': 'us'}],
        error='Failed to fetch manifest: timeout',
    )

    result = map_catalog_downloader.finalize_download(test_session, download, executed)

    assert result.success is False
    assert 'timeout' in (result.error or '')


# ---------------------------------------------------------------------------
# MapExtractDownloader
# ---------------------------------------------------------------------------


def test_extract_prepare_missing_region_sets_error(test_session, test_directory, monkeypatch):
    """A download without settings.region fails fast in prepare."""
    monkeypatch.setattr('modules.map.lib.get_map_directory', lambda: test_directory / 'maps')
    download = Download(
        url='https://x/foo.pmtiles',
        downloader='map_extract',
        settings={},
    )

    prepared = map_extract_downloader.prepare_download(test_session, download)

    assert prepared.error == 'No region in download settings'


def test_extract_prepare_already_done(test_session, test_directory, monkeypatch):
    """If the versioned output already exists, prepare flags already_done so execute
    becomes a no-op."""
    map_dir = test_directory / 'maps'
    map_dir.mkdir(parents=True, exist_ok=True)
    (map_dir / 'us-2024-01.pmtiles').write_bytes(b'pretend pmtiles')
    monkeypatch.setattr('modules.map.lib.get_map_directory', lambda: map_dir)

    download = Download(
        url='https://x/us.pmtiles',
        downloader='map_extract',
        settings={'region': 'us', 'version': '2024-01'},
    )

    prepared = map_extract_downloader.prepare_download(test_session, download)

    assert prepared.already_done is True
    assert prepared.error is None
    assert prepared.output_name == 'us-2024-01.pmtiles'


def test_extract_prepare_cleans_leftover_tmp(test_session, test_directory, monkeypatch):
    """A leftover .tmp file from a prior crashed run is removed in prepare."""
    map_dir = test_directory / 'maps'
    map_dir.mkdir(parents=True, exist_ok=True)
    leftover = map_dir / 'us-2024-01.pmtiles.tmp'
    leftover.write_bytes(b'partial')
    monkeypatch.setattr('modules.map.lib.get_map_directory', lambda: map_dir)

    download = Download(
        url='https://x/us.pmtiles',
        downloader='map_extract',
        settings={'region': 'us', 'version': '2024-01'},
    )

    prepared = map_extract_downloader.prepare_download(test_session, download)

    assert prepared.already_done is False
    assert not leftover.exists()
    assert prepared.tmp_path == leftover  # path is set, just not on disk anymore


def test_extract_finalize_skipped(test_session, test_directory):
    """skipped → success without touching DB."""
    download = Download(url='https://x', downloader='map_extract')
    executed = ExecutedMapExtract(
        region='us', output_path=test_directory / 'us.pmtiles',
        map_directory=test_directory, skipped=True,
    )

    result = map_extract_downloader.finalize_download(test_session, download, executed)

    assert result.success is True
    assert result.location == '/map'


def test_extract_finalize_propagates_error(test_session, test_directory):
    """An execute-phase error becomes a failure DownloadResult."""
    download = Download(url='https://x', downloader='map_extract')
    executed = ExecutedMapExtract(
        region='us', output_path=test_directory / 'us.pmtiles',
        map_directory=test_directory,
        error='Download failed: timeout',
    )

    result = map_extract_downloader.finalize_download(test_session, download, executed)

    assert result.success is False
    assert 'timeout' in (result.error or '')


# ---------------------------------------------------------------------------
# MapSearchIndexDownloader
# ---------------------------------------------------------------------------


def test_search_index_prepare_missing_settings_sets_error(test_session, test_directory, monkeypatch):
    """No region or pmtiles_name in settings → error."""
    monkeypatch.setattr('modules.map.lib.get_map_directory', lambda: test_directory / 'maps')
    download = Download(
        url='https://x/us.search.db',
        downloader='map_search_index',
        settings={'region': 'us'},  # missing pmtiles_name
    )

    prepared = map_search_index_downloader.prepare_download(test_session, download)

    assert prepared.error == 'Missing region or pmtiles_name in settings'


def test_search_index_prepare_pmtiles_missing_sets_error(test_session, test_directory, monkeypatch):
    """If the companion PMTiles file isn't on disk yet, prepare fails so the manager
    can defer + retry."""
    map_dir = test_directory / 'maps'
    map_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr('modules.map.lib.get_map_directory', lambda: map_dir)

    download = Download(
        url='https://x/us.search.db',
        downloader='map_search_index',
        settings={'region': 'us', 'pmtiles_name': 'us-2024-01.pmtiles'},
    )

    prepared = map_search_index_downloader.prepare_download(test_session, download)

    assert prepared.error and 'PMTiles file not found' in prepared.error


def test_search_index_prepare_already_done(test_session, test_directory, monkeypatch):
    """Both pmtiles and search.db exist → already_done short-circuit."""
    map_dir = test_directory / 'maps'
    map_dir.mkdir(parents=True, exist_ok=True)
    (map_dir / 'us-2024-01.pmtiles').write_bytes(b'tiles')
    (map_dir / 'us-2024-01.search.db').write_bytes(b'db')
    monkeypatch.setattr('modules.map.lib.get_map_directory', lambda: map_dir)

    download = Download(
        url='https://x/us.search.db',
        downloader='map_search_index',
        settings={'region': 'us', 'pmtiles_name': 'us-2024-01.pmtiles'},
    )

    prepared = map_search_index_downloader.prepare_download(test_session, download)

    assert prepared.already_done is True
    assert prepared.error is None


def test_search_index_finalize_skipped(test_session):
    """skipped → success."""
    download = Download(url='https://x', downloader='map_search_index')
    executed = ExecutedMapSearchIndex(region='us', skipped=True)

    result = map_search_index_downloader.finalize_download(test_session, download, executed)

    assert result.success is True


def test_search_index_finalize_error(test_session):
    """Error path returns failure with the error message."""
    download = Download(url='https://x', downloader='map_search_index')
    executed = ExecutedMapSearchIndex(region='us', error='Download failed: 500')

    result = map_search_index_downloader.finalize_download(test_session, download, executed)

    assert result.success is False
    assert '500' in (result.error or '')
