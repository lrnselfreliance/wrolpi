"""Phase-split ArchiveDownloader tests.

These tests exercise prepare_download / execute_download / finalize_download in
isolation.  None of them use async_client or test_download_manager — that's the
whole point of the refactor.
"""
import asyncio
import pathlib

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


def make_process_runner_recorder(singlefile: bytes, compressed: bytes = None):
    """Stub Downloader.process_runner: record the call, write the singlefile to the output file
    (the last argument of the command, like single-file does), return a successful CommandResult.

    Capture runs (no --compress-content) write `singlefile`; conversion runs write `compressed`
    (or nothing, when compressed is None, to simulate a failed conversion)."""
    from wrolpi.cmd import CommandResult
    calls = []

    async def process_runner(download, cmd, cwd, **kwargs):
        calls.append(dict(cmd=cmd, cwd=cwd, **kwargs))
        if '--compress-content' not in cmd:
            pathlib.Path(cmd[-1]).write_bytes(singlefile)
        elif compressed is not None:
            pathlib.Path(cmd[-1]).write_bytes(compressed)
        return CommandResult(return_code=0, cancelled=False, stdout=b'', stderr=b'', elapsed=1)

    return process_runner, calls


@pytest.mark.asyncio
async def test_do_singlefile_uses_deno(test_session, test_directory, monkeypatch, compressed_singlefile_factory):
    """single-file is run under Deno (it is designed for it; under node it cannot reach the
    browser CDP on IPv6-enabled hosts and never exits).  The page is captured uncompressed,
    then converted to a compressed (SingleFileZ) file with a second local single-file run."""
    import modules.archive
    singlefile = b'<html><!--\n Page saved with SingleFile \n url: https://example.com \n--></html>'
    compressed = compressed_singlefile_factory()
    process_runner, calls = make_process_runner_recorder(singlefile, compressed)
    monkeypatch.setattr(modules.archive, 'DENO_BIN', '/usr/local/bin/deno')
    monkeypatch.setattr(modules.archive, 'SINGLE_FILE_DENO_SCRIPT',
                        '/usr/local/lib/node_modules/single-file-cli/single-file')
    monkeypatch.setattr(modules.archive, 'CHROMIUM', '/usr/bin/chromium')
    monkeypatch.setattr(archive_downloader, 'process_runner', process_runner)

    prepared = PreparedArchive(url='https://example.com', destination=None,
                               settings={'compress_singlefile': True})
    result, page_html = await archive_downloader.do_singlefile(prepared, make_test_ctx())

    # The compressed file is stored; the uncompressed page is used for readability/screenshot.
    assert result == compressed
    assert page_html == singlefile

    capture, convert = calls
    cmd = capture['cmd']
    assert cmd[2:9] == ('/usr/local/bin/deno', 'run', '--node-modules-dir=manual',
                        '--allow-read', '--allow-write', '--allow-net', '--allow-env')
    assert '/usr/local/lib/node_modules/single-file-cli/single-file' in cmd
    # The capture is always uncompressed.
    assert '--compress-content' not in cmd
    # The singlefile is written to a file; Deno >= 2.3 truncates large --dump-content output.
    assert '--dump-content' not in cmd
    assert cmd[-2] == 'https://example.com'
    assert cmd[-1].endswith('page.html')
    # The browser single-file leaves behind is reaped with the process group.
    assert capture['start_new_session'] is True
    # The browser runs via the stderr-discarding wrapper (Deno >= 2.3 kills it otherwise).
    wrapper = cmd[cmd.index('--browser-executable-path') + 1]
    assert wrapper.endswith('scripts/singlefile_browser_wrapper.sh')
    assert capture['env']['WROLPI_BROWSER'] == '/usr/bin/chromium'

    # The conversion is a local (file://) operation; the page is not fetched again.
    cmd = convert['cmd']
    assert '--compress-content' in cmd
    assert cmd[-2].startswith('file://') and cmd[-2].endswith('page.html')
    assert cmd[-1].endswith('compressed.html')

    # Without the compress setting there is one run, and the page is stored as-is.
    calls.clear()
    prepared = PreparedArchive(url='https://example.com', destination=None, settings={})
    result, page_html = await archive_downloader.do_singlefile(prepared, make_test_ctx())
    assert result == page_html == singlefile
    assert len(calls) == 1

    # When the compression run fails, the uncompressed singlefile is stored instead.
    process_runner, calls = make_process_runner_recorder(singlefile, compressed=None)  # Conversion writes nothing.
    monkeypatch.setattr(archive_downloader, 'process_runner', process_runner)
    prepared = PreparedArchive(url='https://example.com', destination=None,
                               settings={'compress_singlefile': True})
    result, page_html = await archive_downloader.do_singlefile(prepared, make_test_ctx())
    assert len(calls) == 2  # The conversion was attempted.
    assert result == page_html == singlefile

    # A page that has not finished archiving in ten minutes is hung; the timeout reaps it.
    assert archive_downloader.timeout == 10 * 60


@pytest.mark.asyncio
async def test_do_singlefile_node_fallback(test_session, test_directory, monkeypatch):
    """Without Deno, single-file runs under node with the IPv4-fallback fix."""
    import modules.archive
    singlefile = b'<html><!--\n Page saved with SingleFile \n url: https://example.com \n--></html>'
    process_runner, calls = make_process_runner_recorder(singlefile)
    monkeypatch.setattr(modules.archive, 'DENO_BIN', None)
    monkeypatch.setattr(modules.archive, 'SINGLE_FILE_DENO_SCRIPT', None)
    monkeypatch.setattr(modules.archive, 'SINGLE_FILE_BIN', '/usr/local/bin/single-file')
    monkeypatch.setattr(modules.archive, 'CHROMIUM', '/usr/bin/chromium')
    monkeypatch.setattr(archive_downloader, 'process_runner', process_runner)

    prepared = PreparedArchive(url='https://example.com', destination=None, settings={})
    await archive_downloader.do_singlefile(prepared, make_test_ctx())

    call, = calls
    assert call['cmd'][2] == '/usr/local/bin/single-file'
    # node 18 has no IPv4 fallback when "localhost" resolves to ::1 first.
    assert call['env']['NODE_OPTIONS'] == '--enable-network-family-autoselection'
    assert call['start_new_session'] is True


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
