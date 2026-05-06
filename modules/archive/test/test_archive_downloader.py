"""Phase-split ArchiveDownloader tests.

These tests exercise prepare_download / execute_download / finalize_download in
isolation.  None of them use async_client or test_download_manager — that's the
whole point of the refactor.
"""
import asyncio

import pytest

from modules.archive import (
    ExecutedArchive,
    PreparedArchive,
    archive_downloader,
)
from modules.archive.conftest import make_test_ctx
from modules.archive.lib import write_archive_files
from modules.archive.models import Archive
from modules.archive.test.test_lib import make_fake_archive_result
from wrolpi.collections import Collection
from wrolpi.downloader import Download, DownloadResult
from wrolpi.errors import UnrecoverableDownloadError


def test_prepare_max_attempts_raises(test_session):
    """prepare_download enforces the attempt cap before any I/O."""
    download = Download(url='https://example.com/x', downloader='archive', attempts=4)

    with pytest.raises(UnrecoverableDownloadError):
        archive_downloader.prepare_download(test_session, download)


def test_prepare_uses_collection_directory(test_session, test_directory):
    """When a domain Collection has a directory, prepare_download routes the archive there."""
    custom_dir = test_directory / 'archive/News/example.com'
    custom_dir.mkdir(parents=True, exist_ok=True)
    test_session.add(Collection(name='example.com', kind='domain', directory=custom_dir))
    test_session.commit()

    download = Download(url='https://example.com/some-article', downloader='archive', settings={})

    prepared = archive_downloader.prepare_download(test_session, download)

    assert isinstance(prepared, PreparedArchive)
    assert prepared.url == 'https://example.com/some-article'
    assert prepared.destination == custom_dir


def test_prepare_explicit_destination_overrides_collection(test_session, test_directory):
    """An explicit settings['destination'] beats the domain collection's directory."""
    collection_dir = test_directory / 'archive/News/example.com'
    collection_dir.mkdir(parents=True, exist_ok=True)
    test_session.add(Collection(name='example.com', kind='domain', directory=collection_dir))
    test_session.commit()

    explicit_dir = test_directory / 'archive/Special/my-archives'
    explicit_dir.mkdir(parents=True, exist_ok=True)
    download = Download(
        url='https://example.com/some-article',
        downloader='archive',
        settings={'destination': str(explicit_dir)},
    )

    prepared = archive_downloader.prepare_download(test_session, download)

    assert prepared.destination == explicit_dir


@pytest.mark.asyncio
async def test_execute_cancels_via_ctx(test_session, test_directory, monkeypatch):
    """When ctx reports cancelled, the cancel_wrapper that the dispatch puts around
    execute_download returns a cancel DownloadResult — no global download_manager,
    no Sanic shared_ctx."""
    # Force the local-singlefile path so the run_command stub is what blocks.
    import modules.archive
    monkeypatch.setattr(modules.archive, 'DOCKERIZED', False)
    monkeypatch.setattr(modules.archive, 'PYTEST', False)

    async def never_completes(*args, **kwargs):
        await asyncio.sleep(60)
        raise AssertionError('should have been cancelled')

    # Pre-cancelled: the very first poll inside cancel_wrapper aborts the run.
    ctx = make_test_ctx(is_cancelled=lambda: True, run_command_=never_completes)
    prepared = PreparedArchive(
        url='https://example.com/x',
        destination=test_directory / 'archive/example.com',
        settings={},
    )
    prepared.destination.mkdir(parents=True, exist_ok=True)

    # Mirror the dispatch layer: wrap execute_download in cancel_wrapper.
    coro = archive_downloader.execute_download(prepared, ctx)
    result = await archive_downloader.cancel_wrapper(coro, Download(url=prepared.url), ctx=ctx)

    assert isinstance(result, DownloadResult)
    assert result.success is False
    assert 'cancel' in (result.error or '').lower()


@pytest.mark.asyncio
async def test_finalize_adds_tags(async_client, test_session, test_directory, tag_factory):
    """finalize_download applies download.tag_names to the registered Archive.

    Uses async_client because tag_factory's upsert_tag activates a Sanic switch
    (shared_ctx.switches_lock). That's an orthogonal coupling — the rest of
    finalize_download is Sanic-free.
    """
    singlefile, readability, screenshot = make_fake_archive_result()
    destination = test_directory / 'archive/example.com'
    destination.mkdir(parents=True, exist_ok=True)
    written = write_archive_files('https://example.com/x', singlefile, readability, screenshot,
                                  destination=destination)
    executed = ExecutedArchive(written=written)

    tag = await tag_factory()
    download = Download(
        url='https://example.com/x',
        downloader='archive',
        tag_names=[tag.name],
    )

    result = archive_downloader.finalize_download(test_session, download, executed)
    test_session.commit()

    assert result.success is True
    archives = test_session.query(Archive).all()
    assert len(archives) == 1
    archive_tag_names = [tf.tag.name for tf in archives[0].file_group.tag_files]
    assert tag.name in archive_tag_names
