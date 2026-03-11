import hashlib
from http import HTTPStatus
from unittest import mock

from wrolpi import common
from wrolpi.common import DownloadFileInfo
from wrolpi.downloader import Download
from wrolpi.files.downloader import FileDownloader
from wrolpi.test.common import skip_circleci


@skip_circleci
async def test_file_downloader(test_session, make_files_structure, test_directory, await_switches,
                               simple_file_server, test_download_manager, video_file, video_bytes):
    """The FileDownloader can download a file without a metalink file."""
    file_downloader = FileDownloader()
    test_download_manager.register_downloader(file_downloader)

    host, port = simple_file_server.server_address
    url = f'http://{host}:{port}'  # noqa

    # Create download for the video file.
    video_url = f'{url}/{video_file.name}'
    test_download_manager.create_download(test_session, video_url, file_downloader.name,
                                          destination=str(test_directory / 'downloads'))
    test_session.commit()

    await test_download_manager.wait_for_all_downloads()

    download: Download = test_session.query(Download).one()
    assert not download.error, download.error

    # The video was downloaded correctly.
    assert (test_directory / f'downloads/{video_file.name}').is_file()
    assert (test_directory / f'downloads/{video_file.name}').stat().st_size == 1056318
    assert (test_directory / f'downloads/{video_file.name}').read_bytes() == video_bytes


# Minimum Metalink file to download a file.
META4_XML = '''<?xml version="1.0" encoding="UTF-8"?>
<metalink xmlns="urn:ietf:params:xml:ns:metalink">
  <file name="{name}">
    <size>{size}</size>
    <hash type="sha-256">{sha256}</hash>
    <url>{url}/{name}</url>
  </file>
</metalink>
'''


@skip_circleci
async def test_file_downloader_meta4(test_session, make_files_structure, test_directory, await_switches,
                                     simple_file_server, test_download_manager, video_file, video_bytes):
    """The FileDownloader can download a file using a Metalink file."""
    file_downloader = FileDownloader()
    test_download_manager.register_downloader(file_downloader)

    host, port = simple_file_server.server_address
    url = f'http://{host}:{port}'  # noqa

    meta4 = META4_XML.format(
        url=url,
        name=video_file.name,
        size=video_file.stat().st_size,
        sha256=hashlib.sha256(video_bytes).hexdigest(),
    )
    (test_directory / f'{video_file.name}.meta4').write_text(meta4)

    # Ensure files are being served correctly so they can be downloaded.
    video_url = f'{url}/{video_file.name}'
    video_meta4_url = f'{url}/{video_file.name}.meta4'
    async with common.aiohttp_head(video_url, timeout=5) as response:
        assert response.status == HTTPStatus.OK, response.content
    async with common.aiohttp_head(video_meta4_url, timeout=5) as response:
        assert response.status == HTTPStatus.OK, response.content

    # Create download for the video file, this should automatically check for the .meta4 file and use it with aria2c.
    test_download_manager.create_download(test_session, video_url, file_downloader.name,
                                          destination=str(test_directory / 'downloads'))
    test_session.commit()

    await test_download_manager.wait_for_all_downloads()

    download: Download = test_session.query(Download).one()
    assert not download.error, download.error

    # The video was downloaded correctly.
    assert (test_directory / f'downloads/{video_file.name}').is_file()
    assert (test_directory / f'downloads/{video_file.name}').stat().st_size == 1056318
    assert (test_directory / f'downloads/{video_file.name}').read_bytes() == video_bytes
    # The meta4 was saved to a temporary file, but not saved.
    assert not (test_directory / 'downloads/foo.txt.meta4').exists()


async def test_get_download_info_uuid_fallback():
    """get_download_info falls back to the original URL's filename when the resolved name has no extension."""

    class FakeResponse:
        headers = {
            'Content-Type': 'application/octet-stream',
        }
        status = 200

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_head(url, timeout):
        # Simulate a CDN redirect where Location is a UUID path.
        resp = FakeResponse()
        resp.headers = {**resp.headers, 'Location': 'https://cdn.example.com/6f21bc74-aaa8-47f6-ae98-2aebf359df94'}
        yield resp

    with mock.patch('wrolpi.common.aiohttp_head', mock_head):
        info = await common.get_download_info('https://github.com/user/repo/releases/download/v1.0/somefile.tar.gz')

    # The UUID name should be replaced with the original URL's filename.
    assert info.name == 'somefile.tar.gz'


async def test_file_downloader_aria2c_uses_output_flag(test_directory):
    """The aria2c command includes -o with the predicted filename when not using metalink."""
    file_downloader = FileDownloader()

    destination = test_directory / 'downloads'
    destination.mkdir()

    captured_cmd = None

    async def fake_process_runner(download, cmd, dest):
        nonlocal captured_cmd
        captured_cmd = cmd
        # Create the expected output file so the downloader doesn't raise.
        (destination / 'somefile.tar.gz').touch()

        class FakeResult:
            return_code = 0
            stderr = b''

        return FakeResult()

    fake_info = DownloadFileInfo(name='somefile.tar.gz', size=1024, status=200)

    with mock.patch('wrolpi.downloader.get_download_info', mock.AsyncMock(return_value=fake_info)), \
            mock.patch.object(file_downloader, 'process_runner', fake_process_runner):
        download = mock.MagicMock()
        url = 'https://github.com/user/repo/releases/download/v1.0/somefile.tar.gz'
        await file_downloader.download_file(download, url, destination)

    # The command should include -o with the expected filename.
    assert '-o' in captured_cmd
    o_index = captured_cmd.index('-o')
    assert captured_cmd[o_index + 1] == 'somefile.tar.gz'


async def test_file_downloader_meta4_no_output_flag(test_directory):
    """The aria2c command should NOT include -o when using a metalink file."""
    file_downloader = FileDownloader()

    destination = test_directory / 'downloads'
    destination.mkdir()

    captured_cmd = None

    async def fake_process_runner(download, cmd, dest):
        nonlocal captured_cmd
        captured_cmd = cmd
        # Create the expected output file.
        (destination / 'somefile.tar.gz').touch()

        class FakeResult:
            return_code = 0
            stderr = b''

        return FakeResult()

    fake_info = DownloadFileInfo(name='somefile.tar.gz', size=1024, status=200)

    with mock.patch('wrolpi.downloader.get_download_info', mock.AsyncMock(return_value=fake_info)), \
            mock.patch.object(file_downloader, 'get_meta4_contents', mock.AsyncMock(return_value=b'<metalink/>')), \
            mock.patch.object(file_downloader, 'process_runner', fake_process_runner):
        download = mock.MagicMock()
        url = 'https://example.com/somefile.tar.gz'
        await file_downloader.download_file(download, url, destination)

    # When metalink is used, -o should NOT be in the command.
    assert '-o' not in captured_cmd
    # But -M should be present.
    assert '-M' in captured_cmd
