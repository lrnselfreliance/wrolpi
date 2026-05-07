"""Phase-split tests for KiwixCatalogDownloader and KiwixZimDownloader.

These exercise prepare_download / finalize_download (and execute_download for the
catalog, where it's pure HTTP) in isolation — no async_client, no test_download_manager,
no real subprocess.  The Zim downloader's execute phase calls into download_file,
flag_outdated_zim_files, check_zim (subprocess), and upsert_file (own DB session); a
unit test of that full pipeline would effectively be an integration test, so it's
deliberately omitted.
"""
from unittest import mock

import pytest

from modules.archive.conftest import make_test_ctx
from modules.zim.downloader import (
    ExecutedKiwixCatalog,
    ExecutedKiwixZim,
    PreparedKiwixCatalog,
    PreparedKiwixZim,
    kiwix_catalog_downloader,
    kiwix_zim_downloader,
)
from wrolpi.downloader import Download


# ---------------------------------------------------------------------------
# KiwixCatalogDownloader
# ---------------------------------------------------------------------------


def test_catalog_prepare_extracts_parent_and_name(test_session):
    """prepare_download splits the URL into the listing parent and the filename prefix."""
    download = Download(
        url='https://download.kiwix.org/zim/wikipedia/wikipedia_en_all_nopic',
        downloader='kiwix_catalog',
    )

    prepared = kiwix_catalog_downloader.prepare_download(test_session, download)

    assert isinstance(prepared, PreparedKiwixCatalog)
    assert prepared.url == download.url
    assert prepared.parent_url == 'https://download.kiwix.org/zim/wikipedia'
    assert prepared.name == 'wikipedia_en_all_nopic'


@pytest.mark.asyncio
async def test_catalog_execute_picks_latest_matching_zim(test_session):
    """execute_download fetches the parent listing and picks the lexicographically last
    matching .zim — sorted ascending, so the newest YYYY-MM Kiwix filename wins."""
    listing = [
        'wikipedia_en_all_nopic_2024-01.zim',
        'wikipedia_en_all_nopic_2024-06.zim',
        'wikipedia_en_all_nopic_2024-12.zim',
        'wikipedia_en_all_nopic_2024-12.zim.meta4',  # not a .zim file → skipped
        'unrelated_corpus_2024-12.zim',              # different prefix → skipped
    ]

    async def fake_fetch_hrefs(url):
        assert url == 'https://download.kiwix.org/zim/wikipedia'
        return listing

    prepared = PreparedKiwixCatalog(
        url='https://download.kiwix.org/zim/wikipedia/wikipedia_en_all_nopic',
        parent_url='https://download.kiwix.org/zim/wikipedia',
        name='wikipedia_en_all_nopic',
    )

    with mock.patch('modules.zim.downloader.fetch_hrefs', fake_fetch_hrefs):
        executed = await kiwix_catalog_downloader.execute_download(prepared, make_test_ctx())

    assert isinstance(executed, ExecutedKiwixCatalog)
    assert executed.latest_zim_url == \
        'https://download.kiwix.org/zim/wikipedia/wikipedia_en_all_nopic_2024-12.zim'


@pytest.mark.asyncio
async def test_catalog_execute_no_matches(test_session):
    """When the listing has no matching files, executed.latest_zim_url is None."""

    async def fake_fetch_hrefs(url):
        return ['some_other_corpus_2024-01.zim']

    prepared = PreparedKiwixCatalog(
        url='https://download.kiwix.org/zim/wikipedia/wikipedia_en_all_nopic',
        parent_url='https://download.kiwix.org/zim/wikipedia',
        name='wikipedia_en_all_nopic',
    )

    with mock.patch('modules.zim.downloader.fetch_hrefs', fake_fetch_hrefs):
        executed = await kiwix_catalog_downloader.execute_download(prepared, make_test_ctx())

    assert executed.latest_zim_url is None


def test_catalog_finalize_no_match_returns_failure(test_session):
    """latest_zim_url=None → DownloadResult(success=False) with the URL in the error."""
    download = Download(url='https://example.com/zim/foo', downloader='kiwix_catalog')
    executed = ExecutedKiwixCatalog(latest_zim_url=None)

    result = kiwix_catalog_downloader.finalize_download(test_session, download, executed)

    assert result.success is False
    assert 'https://example.com/zim/foo' in (result.error or '')


def test_catalog_finalize_with_match_emits_child_download(test_session):
    """The latest matching URL is emitted as a child download for the kiwix_zim downloader."""
    download = Download(url='https://example.com/zim/foo', downloader='kiwix_catalog')
    executed = ExecutedKiwixCatalog(
        latest_zim_url='https://example.com/zim/foo_2024-12.zim',
    )

    result = kiwix_catalog_downloader.finalize_download(test_session, download, executed)

    assert result.success is True
    assert result.downloads == ['https://example.com/zim/foo_2024-12.zim']


# ---------------------------------------------------------------------------
# KiwixZimDownloader
# ---------------------------------------------------------------------------


def test_zim_prepare_creates_zim_directory(test_session, test_directory, monkeypatch):
    """prepare_download ensures the zim directory exists and returns it on the plan."""
    expected = test_directory / 'zims'
    assert not expected.exists()

    # Override get_zim_directory so we don't depend on wrolpi config defaults.
    monkeypatch.setattr('modules.zim.lib.get_zim_directory', lambda: expected)

    download = Download(
        url='https://example.com/zim/wikipedia_en_all_nopic_2024-12.zim',
        downloader='kiwix_zim',
    )

    prepared = kiwix_zim_downloader.prepare_download(test_session, download)

    assert isinstance(prepared, PreparedKiwixZim)
    assert prepared.url == download.url
    assert prepared.zim_directory == expected
    assert expected.is_dir()


def test_zim_finalize_invalid_zim_returns_failure(test_session, test_directory):
    """is_valid=False → DownloadResult(success=False) with the legacy error message."""
    output_path = test_directory / 'zims/wikipedia_en_all_nopic_2024-12.zim'
    executed = ExecutedKiwixZim(output_path=output_path, is_valid=False)
    download = Download(url='https://example.com/zim/foo', downloader='kiwix_zim')

    result = kiwix_zim_downloader.finalize_download(test_session, download, executed)

    assert result.success is False
    assert result.error == 'Zim file is invalid'


def test_zim_finalize_valid_returns_success(test_session, test_directory):
    """is_valid=True → DownloadResult(success=True) with the generic Kiwix viewer location."""
    output_path = test_directory / 'zims/wikipedia_en_all_nopic_2024-12.zim'
    executed = ExecutedKiwixZim(output_path=output_path, is_valid=True)
    download = Download(url='https://example.com/zim/foo', downloader='kiwix_zim')

    result = kiwix_zim_downloader.finalize_download(test_session, download, executed)

    assert result.success is True
    assert result.location == '/zim'
