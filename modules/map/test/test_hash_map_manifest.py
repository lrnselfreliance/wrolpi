import hashlib
from unittest import mock

import pytest

from wrolpi.scripts.hash_map_manifest import manifest_hashes

META4 = '''<?xml version="1.0" encoding="UTF-8"?>
<metalink xmlns="urn:ietf:params:xml:ns:metalink">
  <file name="{name}">
    <hash type="sha-256">{sha256}</hash>
    <signature mediatype="application/pgp-signature">pretend signature</signature>
  </file>
</metalink>
'''
FILES = {'us-1.pmtiles': b'pmtiles', 'us-1.search.db': b'search', 'terrain-z0-8.pmtiles': b'terrain'}


def _sha256(contents: bytes) -> str:
    return hashlib.sha256(contents).hexdigest()


@pytest.fixture
def served(test_directory, simple_file_server):
    """The published files, served over HTTP, and their manifest."""
    host, port = simple_file_server.server_address
    base = f'http://{host}:{port}'  # noqa
    for name, contents in FILES.items():
        (test_directory / name).write_bytes(contents)
    manifest = {
        'regions': {'us': f'{base}/us-1.pmtiles', 'terrain-z0-8': f'{base}/terrain-z0-8.pmtiles'},
        'search_indexes': {'us': f'{base}/us-1.search.db'},
    }
    # Each file's genuine, signed meta4.
    meta4s = {f'{base}/{name}': META4.format(name=name, sha256=_sha256(contents)) for name, contents in FILES.items()}
    return base, manifest, meta4s


async def _hashes(manifest: dict, meta4s: dict, files_directory=None, signature_valid: bool = True):
    async def get_meta4_contents(url):
        return meta4s[url].encode() if url in meta4s else None

    with mock.patch('wrolpi.scripts.hash_map_manifest.Downloader.get_meta4_contents', get_meta4_contents), \
            mock.patch('modules.map.downloader.verify_gpg_signature', mock.AsyncMock(return_value=signature_valid)):
        return await manifest_hashes(manifest, files_directory)


@pytest.mark.asyncio
@pytest.mark.parametrize('local', [False, True], ids=['downloaded', 'local'])
async def test_manifest_hashes(served, tmp_path, local):
    """Each hash is of the file's bytes (a local copy of the published files, or downloaded), and matches its signed
    meta4."""
    base, manifest, meta4s = served
    files_directory = None
    if local:
        files_directory = tmp_path / 'published'
        files_directory.mkdir()
        for name, contents in FILES.items():
            (files_directory / name).write_bytes(contents)
        # The local copy is read; the server's file is not.
        manifest['regions']['us'] = 'http://127.0.0.1:9/us-1.pmtiles'
        meta4s[manifest['regions']['us']] = meta4s.pop(f'{base}/us-1.pmtiles')

    assert await _hashes(manifest, meta4s, files_directory) == {
        manifest['regions']['us']: _sha256(b'pmtiles'),
        f'{base}/terrain-z0-8.pmtiles': _sha256(b'terrain'),
        f'{base}/us-1.search.db': _sha256(b'search'),
    }


@pytest.mark.asyncio
async def test_manifest_hashes_refuses_a_missing_meta4(served):
    base, manifest, meta4s = served
    del meta4s[f'{base}/us-1.search.db']
    with pytest.raises(RuntimeError):
        await _hashes(manifest, meta4s)


@pytest.mark.asyncio
async def test_manifest_hashes_refuses_an_unsigned_meta4(served):
    _, manifest, meta4s = served
    with pytest.raises(RuntimeError):
        await _hashes(manifest, meta4s, signature_valid=False)


@pytest.mark.asyncio
@pytest.mark.parametrize('name,old_meta4_name', [
    # An older version's signed meta4, its unsigned name rewritten to the current file's.
    ('us-1.search.db', 'us-1.search.db'),
    # Terrain is unversioned, so an older signed meta4 already has the current name.
    ('terrain-z0-8.pmtiles', 'terrain-z0-8.pmtiles'),
])
async def test_manifest_hashes_refuses_an_older_signed_meta4(served, name, old_meta4_name):
    """Only a bare hash is signed in a meta4, so only the file's bytes show which file a signed hash belongs to."""
    base, manifest, meta4s = served
    meta4s[f'{base}/{name}'] = META4.format(name=old_meta4_name, sha256=_sha256(b'older version'))
    with pytest.raises(RuntimeError):
        await _hashes(manifest, meta4s)


@pytest.mark.asyncio
async def test_manifest_hashes_refuses_a_local_copy_that_differs(served, tmp_path):
    _, manifest, meta4s = served
    files_directory = tmp_path / 'published'
    files_directory.mkdir()
    (files_directory / 'us-1.pmtiles').write_bytes(b'something else')
    with pytest.raises(RuntimeError):
        await _hashes(manifest, meta4s, files_directory)
