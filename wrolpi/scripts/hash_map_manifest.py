#!/usr/bin/env python3
"""Add each file's sha256 to the published map manifest, without rebuilding any maps.

Usage:
    python wrolpi/scripts/hash_map_manifest.py <output_dir> [--files DIR] [--manifest-url URL]

Each file is hashed from its bytes: the copy in --files (e.g. the build_map_regions.py output_dir) when it has one,
otherwise downloaded from the CDN.  Every hash must match the file's signed .meta4, and the published manifest's
signature is verified, then the manifest is written to output_dir with a `sha256` of each URL, and signed.  Upload
manifest.json and manifest.json.sig to the CDN.

A .meta4 alone cannot show which file its hash belongs to: only the bare hash is signed, so an older version's .meta4
(with its unsigned name rewritten) passes its signature check.

Manifests from build_map_regions.py already include the hashes.
"""
import argparse
import asyncio
import hashlib
import json
import os
import pathlib
import sys

import requests

# Add project root to path so we can import the map module.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from modules.map.catalog import MANIFEST_URL
from modules.map.downloader import meta4_file_name, verified_meta4_sha256
from modules.map.lib import fetch_manifest
from wrolpi.downloader import Downloader
from wrolpi.scripts.build_map_regions import sign_manifest


def file_sha256(url: str, files_directory: pathlib.Path = None) -> str:
    """sha256 of the file's local copy in `files_directory`, if it has one, otherwise of the file downloaded from
    `url`."""
    h = hashlib.sha256()
    if files_directory and (path := files_directory / meta4_file_name(url)).is_file():
        with path.open('rb') as f:
            for chunk in iter(lambda: f.read(8 * 1024 * 1024), b''):
                h.update(chunk)
    else:
        with requests.get(url, stream=True, timeout=60) as response:
            response.raise_for_status()
            for chunk in response.iter_content(8 * 1024 * 1024):
                h.update(chunk)
    return h.hexdigest()


async def manifest_hashes(manifest: dict, files_directory: pathlib.Path = None) -> dict:
    """{url: sha256} of every file in the manifest, hashed from the file's bytes, each matching its signed .meta4."""
    urls = [*manifest['regions'].values(), *manifest.get('search_indexes', {}).values()]
    hashes = {}
    for url in urls:
        meta4 = await Downloader.get_meta4_contents(url)
        if not meta4 or not (signed_sha256 := await verified_meta4_sha256(meta4)):
            raise RuntimeError(f'No validly signed meta4 for {url}')
        if (sha256 := file_sha256(url, files_directory)) != signed_sha256:
            raise RuntimeError(f'{url} has sha256 {sha256}, its signed meta4 says {signed_sha256}')
        hashes[url] = sha256
        print(f'{sha256}  {url}', flush=True)
    return hashes


def main():
    parser = argparse.ArgumentParser(description='Add each file\'s sha256 to the published map manifest.')
    parser.add_argument('output_dir', help='Directory to write manifest.json and manifest.json.sig to')
    parser.add_argument('--files', type=pathlib.Path,
                        help='Directory of the published files; any not in it are downloaded from the CDN')
    parser.add_argument('--manifest-url', default=MANIFEST_URL, help=f'(default: {MANIFEST_URL})')
    args = parser.parse_args()

    manifest = asyncio.run(fetch_manifest(args.manifest_url))
    manifest['sha256'] = asyncio.run(manifest_hashes(manifest, args.files))

    os.makedirs(args.output_dir, exist_ok=True)
    manifest_path = os.path.join(os.path.abspath(args.output_dir), 'manifest.json')
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)
    print(f'\nManifest written to: {manifest_path}')
    sign_manifest(manifest_path)
    print('Upload manifest.json and manifest.json.sig to the CDN.')


if __name__ == '__main__':
    main()
