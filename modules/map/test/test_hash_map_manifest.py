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
MANIFEST = {
    'regions': {'us': 'https://x/us-1.pmtiles'},
    'search_indexes': {'us': 'https://x/us-1.search.db'},
}


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


async def _hashes(meta4s: dict, signature_valid: bool = True):
    async def get_meta4_contents(url):
        return meta4s[url].encode() if url in meta4s else None

    with mock.patch('wrolpi.scripts.hash_map_manifest.Downloader.get_meta4_contents', get_meta4_contents), \
            mock.patch('modules.map.downloader.verify_gpg_signature', mock.AsyncMock(return_value=signature_valid)):
        return await manifest_hashes(MANIFEST)


@pytest.mark.asyncio
async def test_manifest_hashes():
    meta4s = {
        'https://x/us-1.pmtiles': META4.format(name='us-1.pmtiles', sha256=_sha256('pmtiles')),
        'https://x/us-1.search.db': META4.format(name='us-1.search.db', sha256=_sha256('search')),
    }
    assert await _hashes(meta4s) == {
        'https://x/us-1.pmtiles': _sha256('pmtiles'),
        'https://x/us-1.search.db': _sha256('search'),
    }


@pytest.mark.asyncio
@pytest.mark.parametrize('meta4s,signature_valid', [
    # A file has no meta4.
    ({'https://x/us-1.pmtiles': META4.format(name='us-1.pmtiles', sha256=_sha256('pmtiles'))}, True),
    # The meta4s are not signed by WROLPi.
    ({'https://x/us-1.pmtiles': META4.format(name='us-1.pmtiles', sha256=_sha256('pmtiles')),
      'https://x/us-1.search.db': META4.format(name='us-1.search.db', sha256=_sha256('search'))}, False),
    # The search index's URL serves the meta4 of another file.
    ({'https://x/us-1.pmtiles': META4.format(name='us-1.pmtiles', sha256=_sha256('pmtiles')),
      'https://x/us-1.search.db': META4.format(name='us-0.search.db', sha256=_sha256('old search'))}, True),
    # ...renamed, which only the duplicate hash reveals.
    ({'https://x/us-1.pmtiles': META4.format(name='us-1.pmtiles', sha256=_sha256('pmtiles')),
      'https://x/us-1.search.db': META4.format(name='us-1.search.db', sha256=_sha256('pmtiles'))}, True),
], ids=['missing', 'unsigned', 'wrong_meta4', 'duplicate_hash'])
async def test_manifest_hashes_refuses(meta4s, signature_valid):
    with pytest.raises(RuntimeError):
        await _hashes(meta4s, signature_valid)
