import hashlib
from http import HTTPStatus

from wrolpi import common
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
    test_download_manager.create_download(video_url, file_downloader.name, test_session,
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
    test_download_manager.create_download(video_url, file_downloader.name, test_session,
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
