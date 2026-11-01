"""Phase-split tests for MapCatalogDownloader / MapExtractDownloader / MapSearchIndexDownloader.

These exercise prepare_download and finalize_download in isolation — no async_client,
no test_download_manager, no real subprocess.  Execute is tested only for refusing a download
without a signed hash; the paths that drive download_file + GPG verification + filesystem
rename are integration territory and are deliberately omitted; the parent download_file ctx
threading is already covered by the FileDownloader migration tests.
"""
import hashlib
from unittest import mock
from xml.etree import ElementTree

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
from wrolpi.test.common import skip_ci


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


def test_catalog_finalize_replaces_stale_extract_download(test_session, test_directory, test_download_manager,
                                                          monkeypatch):
    """A new manifest version replaces the region's old extract Download (found by its settings' region)."""
    monkeypatch.setattr('modules.map.lib.get_map_directory', lambda: test_directory / 'maps')
    test_session.add(Download(url='https://x/us-2024-01.pmtiles', downloader='map_extract',
                              settings={'region': 'us', 'version': '2024-01'}))
    test_session.commit()

    download = Download(url='https://x/manifest.json', downloader='map_catalog')
    executed = ExecutedMapCatalog(
        manifest={'regions': {'us': 'https://x/us-2024-02.pmtiles'}, 'version': '2024-02'},
        subscribed_regions=[{'region': 'us'}],
    )
    result = map_catalog_downloader.finalize_download(test_session, download, executed)
    assert result.success is True, result.error

    downloads = test_session.query(Download).filter_by(downloader='map_extract').all()
    assert [(i.url, i.settings['version']) for i in downloads] == [('https://x/us-2024-02.pmtiles', '2024-02')]


@pytest.mark.parametrize('has_search_download', [True, False])
def test_extract_finalize_builds_search_index(test_session, test_directory, has_search_download):
    """The search index is built locally unless a search index Download exists for the region."""
    if has_search_download:
        test_session.add(Download(url='https://x/us.search.db', downloader='map_search_index',
                                  settings={'region': 'us', 'pmtiles_name': 'us-2024-01.pmtiles'}))
        test_session.commit()
    download = Download(url='https://x/us.pmtiles', downloader='map_extract')
    executed = ExecutedMapExtract(
        region='us', output_path=test_directory / 'us-2024-01.pmtiles', map_directory=test_directory,
    )

    with mock.patch('modules.map.search.rebuild_search_index') as rebuild:
        result = map_extract_downloader.finalize_download(test_session, download, executed)

    assert result.success is True
    assert rebuild.called is not has_search_download


# ---------------------------------------------------------------------------
# Signed hash required before downloading
# ---------------------------------------------------------------------------


def _prepared_extract(map_dir, sha256: str = None):
    return map_extract_downloader.prepare_download(None, Download(
        url='https://x/us-2024-01.pmtiles', downloader='map_extract',
        settings={'region': 'us', 'version': '2024-01', 'sha256': sha256},
    ))


def _prepared_search_index(map_dir, sha256: str = None):
    (map_dir / 'us-2024-01.pmtiles').write_bytes(b'pretend pmtiles')
    return map_search_index_downloader.prepare_download(None, Download(
        url='https://x/us-2024-01.search.db', downloader='map_search_index',
        settings={'region': 'us', 'pmtiles_name': 'us-2024-01.pmtiles', 'sha256': sha256},
    ))


@pytest.mark.asyncio
@pytest.mark.parametrize('downloader,prepare', [
    (map_extract_downloader, _prepared_extract),
    (map_search_index_downloader, _prepared_search_index),
], ids=['extract', 'search_index'])
@pytest.mark.parametrize('has_meta4,signature_valid', [
    (False, True),  # The CDN has no .meta4 (or it could not be fetched).
    (True, False),  # The .meta4's hash is not signed by WROLPi.
], ids=['no_meta4', 'bad_signature'])
async def test_map_download_requires_signed_hash(test_directory, monkeypatch, downloader, prepare, has_meta4,
                                                 signature_valid):
    """A map file is never downloaded unless its .meta4 carries a hash signed by WROLPi; aria2c then refuses any
    file that does not match that hash."""
    map_dir = test_directory / 'maps'
    map_dir.mkdir()
    monkeypatch.setattr('modules.map.lib.get_map_directory', lambda: map_dir)
    prepared = prepare(map_dir)
    download = Download(url=f'https://x/{prepared.region}.file')
    meta4 = INJECTED_META4.format(url=download.url).encode() if has_meta4 else None

    with mock.patch.object(downloader, 'get_meta4_contents', mock.AsyncMock(return_value=meta4)), \
            mock.patch('modules.map.downloader.verify_gpg_signature', mock.AsyncMock(return_value=signature_valid)), \
            mock.patch.object(downloader, 'download_file', mock.AsyncMock()) as download_file:
        executed = await downloader.execute_download(prepared, make_test_ctx(), download)

    assert executed.error and 'us' in executed.error
    download_file.assert_not_called()


GENUINE_SHA256 = hashlib.sha256(b'genuine contents').hexdigest()
TAMPERED_SHA512 = hashlib.sha512(b'tampered contents').hexdigest()
# Only the sha-256 hash of a meta4 is signed; everything else in it is whatever the server sent.
INJECTED_META4 = f'''<?xml version="1.0" encoding="UTF-8"?>
<metalink xmlns="urn:ietf:params:xml:ns:metalink">
  <file name="us-2024-01.pmtiles">
    <hash type="sha-256">{GENUINE_SHA256}</hash>
    <signature mediatype="application/pgp-signature">pretend signature</signature>
    <hash type="sha-512">{TAMPERED_SHA512}</hash>
    <pieces length="1" type="sha-512"><hash>{TAMPERED_SHA512}</hash></pieces>
    <url>{{url}}</url>
    <url>https://elsewhere.example/us-2024-01.pmtiles</url>
  </file>
  <file name="extra.pmtiles">
    <url>https://elsewhere.example/extra.pmtiles</url>
  </file>
</metalink>
'''


@pytest.mark.asyncio
@pytest.mark.parametrize('downloader,prepare', [
    (map_extract_downloader, _prepared_extract),
    (map_search_index_downloader, _prepared_search_index),
], ids=['extract', 'search_index'])
async def test_map_download_passes_only_the_signed_hash(test_directory, monkeypatch, downloader, prepare):
    """aria2c gets a meta4 holding only the signed sha-256 hash and the download URL, never the downloaded meta4,
    whose other hashes, pieces, files, and URLs are not signed."""
    map_dir = test_directory / 'maps'
    map_dir.mkdir()
    monkeypatch.setattr('modules.map.lib.get_map_directory', lambda: map_dir)
    prepared = prepare(map_dir)
    url = 'https://x/us-2024-01.pmtiles'
    meta4 = INJECTED_META4.format(url=url).encode()

    with mock.patch.object(downloader, 'get_meta4_contents', mock.AsyncMock(return_value=meta4)), \
            mock.patch('modules.map.downloader.verify_gpg_signature', mock.AsyncMock(return_value=True)), \
            mock.patch.object(downloader, 'download_file', mock.AsyncMock(side_effect=RuntimeError('stop'))) as df:
        await downloader.execute_download(prepared, make_test_ctx(), Download(url=url))

    passed = ElementTree.fromstring(df.call_args.kwargs['meta4_xml'])
    ns = {'ml': 'urn:ietf:params:xml:ns:metalink'}
    files = passed.findall('ml:file', ns)
    assert len(files) == 1
    assert [(i.get('type'), i.text) for i in files[0].iter('{urn:ietf:params:xml:ns:metalink}hash')] \
           == [('sha-256', GENUINE_SHA256)]
    assert [i.text for i in files[0].findall('ml:url', ns)] == [url]
    assert files[0].find('ml:pieces', ns) is None


@pytest.mark.asyncio
@pytest.mark.parametrize('sha256', ['', 'not-hex', GENUINE_SHA256 + '00', f'{GENUINE_SHA256[:-1]}<'])
async def test_map_download_refuses_a_malformed_signed_hash(test_directory, monkeypatch, sha256):
    map_dir = test_directory / 'maps'
    map_dir.mkdir()
    monkeypatch.setattr('modules.map.lib.get_map_directory', lambda: map_dir)
    prepared = _prepared_extract(map_dir)
    meta4 = INJECTED_META4.format(url='https://x/us-2024-01.pmtiles').replace(GENUINE_SHA256, sha256, 1)

    with mock.patch.object(map_extract_downloader, 'get_meta4_contents', mock.AsyncMock(return_value=meta4.encode())), \
            mock.patch('modules.map.downloader.verify_gpg_signature', mock.AsyncMock(return_value=True)), \
            mock.patch.object(map_extract_downloader, 'download_file', mock.AsyncMock()) as download_file:
        executed = await map_extract_downloader.execute_download(prepared, make_test_ctx(), Download(url='https://x/a'))

    assert executed.error
    download_file.assert_not_called()


@skip_ci
@pytest.mark.asyncio
async def test_map_download_refuses_tampered_file_with_injected_hash(test_directory, monkeypatch,
                                                                     simple_file_server):
    """Real aria2c: a server that adds a sha-512 of its tampered file to a genuinely signed meta4 does not get the
    tampered file accepted, the rejected file is not left where the next attempt would take it as downloaded, and a
    retry downloads the genuine file."""
    map_dir = test_directory / 'maps'
    map_dir.mkdir()
    monkeypatch.setattr('modules.map.lib.get_map_directory', lambda: map_dir)
    served = test_directory / 'us-2024-01.pmtiles'
    served.write_bytes(b'tampered contents')
    host, port = simple_file_server.server_address
    url = f'http://{host}:{port}/us-2024-01.pmtiles'  # noqa

    meta4 = INJECTED_META4.format(url=url).encode()
    with mock.patch.object(map_extract_downloader, 'get_meta4_contents', mock.AsyncMock(return_value=meta4)), \
            mock.patch('modules.map.downloader.verify_gpg_signature', mock.AsyncMock(return_value=True)):
        prepared = _prepared_extract(map_dir)
        executed = await map_extract_downloader.execute_download(prepared, make_test_ctx(), Download(url=url))
        assert executed.error
        assert list(map_dir.glob('*.pmtiles')) == []
        # The next attempt does not skip the download.
        assert not _prepared_extract(map_dir).already_done

        # The server now serves the genuine file.
        served.write_bytes(b'genuine contents')
        prepared = _prepared_extract(map_dir)
        executed = await map_extract_downloader.execute_download(prepared, make_test_ctx(), Download(url=url))
        assert not executed.error, executed.error
        assert prepared.output_path.read_bytes() == b'genuine contents'


@pytest.mark.asyncio
@pytest.mark.parametrize('downloader,prepare', [
    (map_extract_downloader, _prepared_extract),
    (map_search_index_downloader, _prepared_search_index),
], ids=['extract', 'search_index'])
async def test_map_download_moves_only_the_checked_file(test_directory, monkeypatch, downloader, prepare):
    """Only the file aria2c checked (named in the meta4 WROLPi wrote) is moved into place, never the path
    download_file reports, which comes from the server's HEAD response (Content-Disposition, redirects)."""
    map_dir = test_directory / 'maps'
    map_dir.mkdir()
    monkeypatch.setattr('modules.map.lib.get_map_directory', lambda: map_dir)
    prepared = prepare(map_dir)
    url = 'https://x/us-2024-01.pmtiles'
    # An unchecked leftover of an interrupted download, which the server names in its HEAD response.
    leftover = map_dir / '.partial/other.pmtiles'
    leftover.parent.mkdir()
    leftover.write_bytes(b'tampered contents')

    meta4 = INJECTED_META4.format(url=url).encode()
    with mock.patch.object(downloader, 'get_meta4_contents', mock.AsyncMock(return_value=meta4)), \
            mock.patch('modules.map.downloader.verify_gpg_signature', mock.AsyncMock(return_value=True)), \
            mock.patch.object(downloader, 'download_file', mock.AsyncMock(return_value=leftover)):
        executed = await downloader.execute_download(prepared, make_test_ctx(), Download(url=url))

    assert executed.error
    assert leftover.read_bytes() == b'tampered contents'
    assert {i.name for i in map_dir.iterdir()} <= {'.partial', 'us-2024-01.pmtiles'}
    assert not any(i.read_bytes() == b'tampered contents' for i in map_dir.glob('*.*') if i.is_file())


@pytest.mark.asyncio
@pytest.mark.parametrize('url', ['https://x/', 'https://x/..', 'https://x/.hidden', 'https://x/a%2F..'])
async def test_map_download_refuses_unusable_file_name(test_directory, monkeypatch, url):
    map_dir = test_directory / 'maps'
    map_dir.mkdir()
    monkeypatch.setattr('modules.map.lib.get_map_directory', lambda: map_dir)
    prepared = _prepared_extract(map_dir)

    meta4 = INJECTED_META4.format(url=url).encode()
    with mock.patch.object(map_extract_downloader, 'get_meta4_contents', mock.AsyncMock(return_value=meta4)), \
            mock.patch('modules.map.downloader.verify_gpg_signature', mock.AsyncMock(return_value=True)), \
            mock.patch.object(map_extract_downloader, 'download_file', mock.AsyncMock()) as download_file:
        executed = await map_extract_downloader.execute_download(prepared, make_test_ctx(), Download(url=url))

    assert executed.error
    download_file.assert_not_called()


# ---------------------------------------------------------------------------
# Hashes from the signed manifest
# ---------------------------------------------------------------------------

MANIFEST_SHA256 = hashlib.sha256(b'manifest contents').hexdigest()


def test_catalog_finalize_copies_manifest_hashes(test_session, test_directory, test_download_manager, monkeypatch):
    """Each child download gets its file's hash from the signed manifest."""
    map_dir = test_directory / 'maps'
    monkeypatch.setattr('modules.map.lib.get_map_directory', lambda: map_dir)
    pmtiles_url, search_url = 'https://x/us-2024-02.pmtiles', 'https://x/us-2024-02.search.db'
    executed = ExecutedMapCatalog(
        manifest={'regions': {'us': pmtiles_url}, 'search_indexes': {'us': search_url}, 'version': '2024-02',
                  'sha256': {pmtiles_url: MANIFEST_SHA256, search_url: GENUINE_SHA256}},
        subscribed_regions=[{'region': 'us'}],
    )
    download = Download(url='https://x/manifest.json', downloader='map_catalog')
    result = map_catalog_downloader.finalize_download(test_session, download, executed)
    assert result.success is True, result.error

    hashes = {i.downloader: i.settings.get('sha256') for i in test_session.query(Download)}
    assert hashes == {'map_extract': MANIFEST_SHA256, 'map_search_index': GENUINE_SHA256}


@pytest.mark.asyncio
@pytest.mark.parametrize('downloader,prepare', [
    (map_extract_downloader, _prepared_extract),
    (map_search_index_downloader, _prepared_search_index),
], ids=['extract', 'search_index'])
async def test_map_download_uses_the_manifest_hash(test_directory, monkeypatch, downloader, prepare):
    """A hash from the signed manifest is the one aria2c checks.  A meta4 signs only a bare hash, so any genuine
    meta4 (an older version, another region) would pass its own signature check."""
    map_dir = test_directory / 'maps'
    map_dir.mkdir()
    monkeypatch.setattr('modules.map.lib.get_map_directory', lambda: map_dir)
    prepared = prepare(map_dir, sha256=MANIFEST_SHA256)
    url = 'https://x/us-2024-01.pmtiles'
    # A genuinely signed meta4, but of some other file.
    meta4 = INJECTED_META4.format(url=url).encode()

    with mock.patch.object(downloader, 'get_meta4_contents', mock.AsyncMock(return_value=meta4)) as get_meta4, \
            mock.patch('modules.map.downloader.verify_gpg_signature', mock.AsyncMock(return_value=True)), \
            mock.patch.object(downloader, 'download_file', mock.AsyncMock(side_effect=RuntimeError('stop'))) as df:
        await downloader.execute_download(prepared, make_test_ctx(), Download(url=url))

    get_meta4.assert_not_called()
    passed = ElementTree.fromstring(df.call_args.kwargs['meta4_xml'])
    assert [i.text for i in passed.iter('{urn:ietf:params:xml:ns:metalink}hash')] == [MANIFEST_SHA256]


@pytest.mark.asyncio
@pytest.mark.parametrize('downloader,prepare', [
    (map_extract_downloader, _prepared_extract),
    (map_search_index_downloader, _prepared_search_index),
], ids=['extract', 'search_index'])
async def test_map_download_refuses_a_malformed_manifest_hash(test_directory, monkeypatch, downloader, prepare):
    map_dir = test_directory / 'maps'
    map_dir.mkdir()
    monkeypatch.setattr('modules.map.lib.get_map_directory', lambda: map_dir)
    prepared = prepare(map_dir, sha256='not-a-hash')
    meta4 = INJECTED_META4.format(url='https://x/a.pmtiles').encode()

    with mock.patch.object(downloader, 'get_meta4_contents', mock.AsyncMock(return_value=meta4)), \
            mock.patch('modules.map.downloader.verify_gpg_signature', mock.AsyncMock(return_value=True)), \
            mock.patch.object(downloader, 'download_file', mock.AsyncMock()) as download_file:
        executed = await downloader.execute_download(prepared, make_test_ctx(), Download(url='https://x/a.pmtiles'))

    assert executed.error
    download_file.assert_not_called()
