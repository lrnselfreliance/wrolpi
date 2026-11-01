#!/usr/bin/env python3
"""Add each file's sha256 to the published map manifest, without rebuilding any maps.

Usage:
    python wrolpi/scripts/hash_map_manifest.py <output_dir> [--manifest-url URL]

The published manifest's signature and every file's signed .meta4 are verified, then the manifest is written to
output_dir with a `sha256` of each URL, and signed.  Upload manifest.json and manifest.json.sig to the CDN.

Manifests from build_map_regions.py already include the hashes.
"""
import argparse
import asyncio
import json
import os
import sys
from xml.etree import ElementTree as ET

# Add project root to path so we can import the map module.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from modules.map.catalog import MANIFEST_URL
from modules.map.downloader import METALINK_NS, meta4_file_name, verified_meta4_sha256
from modules.map.lib import fetch_manifest
from wrolpi.downloader import Downloader
from wrolpi.scripts.build_map_regions import sign_manifest


async def manifest_hashes(manifest: dict) -> dict:
    """{url: sha256} of every file in the manifest, from each file's signed .meta4."""
    urls = [*manifest['regions'].values(), *manifest.get('search_indexes', {}).values()]
    hashes = {}
    for url in urls:
        meta4 = await Downloader.get_meta4_contents(url)
        if not meta4 or not (sha256 := await verified_meta4_sha256(meta4)):
            raise RuntimeError(f'No validly signed meta4 for {url}')
        # The name is not signed, but build_map_regions.py writes each file's own name; any other is not its meta4.
        file_el = ET.fromstring(meta4).find('ml:file', METALINK_NS)
        if file_el.get('name') != meta4_file_name(url):
            raise RuntimeError(f'The meta4 for {url} names {file_el.get("name")!r}')
        hashes[url] = sha256
        print(f'{sha256}  {url}')

    if len(set(hashes.values())) != len(hashes):
        raise RuntimeError('Two files have the same hash; a meta4 was served for the wrong file')
    return hashes


def main():
    parser = argparse.ArgumentParser(description='Add each file\'s sha256 to the published map manifest.')
    parser.add_argument('output_dir', help='Directory to write manifest.json and manifest.json.sig to')
    parser.add_argument('--manifest-url', default=MANIFEST_URL, help=f'(default: {MANIFEST_URL})')
    args = parser.parse_args()

    manifest = asyncio.run(fetch_manifest(args.manifest_url))
    manifest['sha256'] = asyncio.run(manifest_hashes(manifest))

    os.makedirs(args.output_dir, exist_ok=True)
    manifest_path = os.path.join(os.path.abspath(args.output_dir), 'manifest.json')
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)
    print(f'\nManifest written to: {manifest_path}')
    sign_manifest(manifest_path)
    print('Upload manifest.json and manifest.json.sig to the CDN.')


if __name__ == '__main__':
    main()
