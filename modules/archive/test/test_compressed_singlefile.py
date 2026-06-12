"""Tests for compressed (SingleFileZ) singlefile Archives.

A compressed singlefile is a self-extracting HTML file which is also a valid ZIP containing the
uncompressed page as index.html.  Only the singlefile .html is compressed; readability files are
always written uncompressed.
"""
import base64
import pathlib
import zipfile

import pytest

import modules.archive
from modules.archive import archive_downloader, PreparedArchive, model_archive
from modules.archive.conftest import make_test_ctx
from modules.archive.lib import (
    is_compressed_singlefile,
    get_compressed_singlefile_index,
    get_url_from_singlefile,
    is_singlefile_file,
    write_archive_files,
)
from modules.archive.test.test_lib import make_fake_archive_result
from wrolpi.downloader import Download
from wrolpi.files.lib import get_mimetype, _mimetype_suffix_map
from wrolpi.files.models import FileGroup
from wrolpi.schema import DownloadRequest


def test_is_compressed_singlefile(compressed_singlefile_factory, singlefile_contents_factory):
    compressed = compressed_singlefile_factory()
    assert is_compressed_singlefile(compressed) is True

    # A regular singlefile is not compressed.
    assert is_compressed_singlefile(singlefile_contents_factory().encode()) is False
    # Garbage is not compressed.
    assert is_compressed_singlefile(b'not a zip') is False

    # The uncompressed page can be extracted.
    index = get_compressed_singlefile_index(compressed)
    assert b'test compressed singlefile' in index
    assert b'<title>compressed title</title>' in index


def test_get_url_from_compressed_singlefile(compressed_singlefile_factory):
    """The URL can be extracted from the plain-text prelude despite the binary ZIP tail."""
    compressed = compressed_singlefile_factory(url='https://wrolpi.org/some-article')
    assert get_url_from_singlefile(compressed) == 'https://wrolpi.org/some-article'


@pytest.mark.parametrize(
    'name,expected', [
        ('2000-01-01-00-00-00_Some NA.html', True),  # Matches the WROLPi Archive file name.
        ('foo.html', True),  # Detected by the SingleFile header in the prelude.
        ('foo.txt', False),
    ]
)
def test_is_singlefile_file_compressed(name, expected, make_files_structure, compressed_singlefile_factory):
    """A compressed singlefile is recognized even though it has a binary ZIP tail."""
    path, = make_files_structure([name])
    path.write_bytes(compressed_singlefile_factory())
    assert is_singlefile_file(path) == expected


def test_compressed_singlefile_mimetype(make_files_structure, compressed_singlefile_factory):
    """A compressed singlefile must be `text/html` so the archive modeler finds it."""
    # `magic` reports application/octet-stream for the real (binary) compressed singlefile.
    assert _mimetype_suffix_map(pathlib.Path('foo.html'), 'application/octet-stream') == 'text/html'

    path, = make_files_structure(['archive/2000-01-01-00-00-00_compressed.html'])
    path.write_bytes(compressed_singlefile_factory())
    assert get_mimetype(path) == 'text/html'


def test_write_archive_files_compressed(test_directory, test_session, image_bytes_factory,
                                        compressed_singlefile_factory):
    """The compressed singlefile is written verbatim (prettifying would corrupt the ZIP);
    readability files are written uncompressed."""
    compressed = compressed_singlefile_factory()
    readability = dict(content='<html>readability content</html>', textContent='readability text', title='a title')
    destination = test_directory / 'archive/example.com'
    destination.mkdir(parents=True)

    written = write_archive_files('https://example.com', compressed, readability, image_bytes_factory(),
                                  destination=destination)

    singlefile_path = next(i for i in written.paths if i.suffix == '.html' and '.readability' not in i.name)
    # The file on disk is unchanged, and still a valid ZIP.
    assert singlefile_path.read_bytes() == compressed
    assert zipfile.is_zipfile(singlefile_path)

    # Readability files are plain text, not compressed.
    readability_path = next(i for i in written.paths if i.name.endswith('.readability.html'))
    assert 'readability content' in readability_path.read_text()
    readability_txt_path = next(i for i in written.paths if i.name.endswith('.readability.txt'))
    assert 'readability text' in readability_txt_path.read_text()


def test_readability_images_inlined(test_directory, test_session, compressed_singlefile_factory):
    """Readability extracted from a compressed singlefile references images by relative ZIP paths;
    they are inlined as data URIs so the readability file is self-contained."""
    from modules.archive.lib import inline_compressed_singlefile_resources

    compressed = compressed_singlefile_factory()
    expected_data_uri = 'data:image/png;base64,' + base64.b64encode(b'\x89PNG fake image bytes').decode()

    # Relative and absolutized ZIP paths are inlined; data/external URLs and unknown paths are
    # left alone.  readability-extractor absolutizes relative srcs against the page URL.
    content = '<html><body>' \
              '<img src="images/0.png" srcset="images/0.png 1x">' \
              '<img src="https://example.com/images/0.png">' \
              '<img src="https://other.com/remote.png">' \
              '<img src="data:image/png;base64,QUJD">' \
              '<img src="images/does-not-exist.png">' \
              '<p>article text</p></body></html>'
    inlined = inline_compressed_singlefile_resources(content, compressed, 'https://example.com/page')
    assert inlined.count(expected_data_uri) == 2  # The relative and the absolutized form.
    assert 'srcset' not in inlined
    assert 'https://other.com/remote.png' in inlined
    assert 'data:image/png;base64,QUJD' in inlined
    assert 'images/does-not-exist.png' in inlined

    # write_archive_files inlines the readability content of compressed singlefiles.
    readability = dict(content=content, textContent='article text', title='a title')
    destination = test_directory / 'archive/example.com'
    destination.mkdir(parents=True)
    written = write_archive_files('https://example.com', compressed, readability, None, destination=destination)

    readability_path = next(i for i in written.paths if i.name.endswith('.readability.html'))
    text = readability_path.read_text()
    assert expected_data_uri in text
    assert 'src="images/0.png"' not in text


def test_write_archive_files_compressed_title_fallback(test_directory, test_session, compressed_singlefile_factory):
    """Without a readability title, the title comes from the ZIP's index.html."""
    compressed = compressed_singlefile_factory(title='the fallback title')
    destination = test_directory / 'archive/example.com'
    destination.mkdir(parents=True)

    written = write_archive_files('https://example.com', compressed, None, None, destination=destination)

    singlefile_path = next(i for i in written.paths if i.suffix == '.html' and '.readability' not in i.name)
    assert 'the fallback title' in singlefile_path.name
    assert singlefile_path.read_bytes() == compressed


@pytest.mark.asyncio
async def test_execute_download_compressed(test_session, test_directory, monkeypatch, compressed_singlefile_factory):
    """The compress_singlefile setting is forwarded to the archive service, and the compressed
    bytes returned are written to disk unchanged."""
    compressed = compressed_singlefile_factory()
    _, readability, screenshot = make_fake_archive_result()
    request_archive_kwargs = {}

    async def mock_request_archive(url, compress=False):
        request_archive_kwargs['compress'] = compress
        return compressed, readability, screenshot

    monkeypatch.setattr(modules.archive, 'request_archive', mock_request_archive)

    destination = test_directory / 'archive/example.com'
    destination.mkdir(parents=True)
    prepared = PreparedArchive(
        url='https://example.com',
        destination=destination,
        settings={'compress_singlefile': True},
    )

    executed = await archive_downloader.execute_download(prepared, make_test_ctx())

    assert request_archive_kwargs['compress'] is True
    singlefile_path = next(i for i in executed.written.paths if i.suffix == '.html' and '.readability' not in i.name)
    assert singlefile_path.read_bytes() == compressed


@pytest.mark.asyncio
async def test_model_archive_compressed(async_client, test_session, test_directory, make_files_structure,
                                        compressed_singlefile_factory):
    """A compressed singlefile on disk (without readability files) can be modeled as an Archive;
    the title and URL come from the compressed file itself.

    async_client is required because get_or_create_domain_collection activates a Sanic switch."""
    path, = make_files_structure(['archive/2000-01-01-00-00-00_compressed.html'])
    path.write_bytes(compressed_singlefile_factory(url='https://example.com/article', title='compressed title'))

    file_group = FileGroup.from_paths(test_session, path)
    test_session.flush()

    archive = model_archive(test_session, file_group)
    test_session.commit()

    assert archive.file_group.url == 'https://example.com/article'
    assert archive.file_group.title == 'compressed title'
    assert archive.collection.name == 'example.com'


def test_download_request_compress_singlefile():
    """compress_singlefile=True survives DownloadRequest settings validation."""
    request = DownloadRequest(
        urls=['https://example.com'],
        downloader='archive',
        settings=dict(compress_singlefile=True),
    )
    assert request.settings['compress_singlefile'] is True


def test_rss_forwards_compress_singlefile(test_session):
    """RSSDownloader passes compress_singlefile on to the child archive downloads."""
    from wrolpi.downloader import rss_downloader, ExecutedRSS

    download = Download(
        url='https://example.com/feed',
        downloader='rss',
        sub_downloader='archive',
        settings={'compress_singlefile': True},
    )
    executed = ExecutedRSS(yt_channel_id=None, candidate_urls=['https://example.com/article'])

    result = rss_downloader.finalize_download(test_session, download, executed)

    assert result.success is True
    assert result.downloads == ['https://example.com/article']
    assert result.settings['compress_singlefile'] is True
