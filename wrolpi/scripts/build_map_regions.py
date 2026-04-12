#!/usr/bin/env python3
"""Extract all map regions from a planet PMTiles file and generate a CDN manifest.

Usage:
    python scripts/build_map_regions.py <planet.pmtiles> <version> <output_dir> [--cdn-base URL]

Example:
    python scripts/build_map_regions.py planet-20260329.pmtiles 20260329 ./cdn-output/

This script:
  1. Reads region definitions from modules/map/catalog.py
  2. Runs `pmtiles extract` for each bbox region
  3. Generates manifest.json with direct download URLs for each region
  4. Prints a summary of all extracted files and sizes

Requirements:
  - pmtiles CLI installed (https://github.com/protomaps/go-pmtiles)
  - Planet PMTiles file already downloaded
  - Terrain file must be placed in output_dir manually (not extracted from planet)
"""
import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import time

import requests

# Add project root to path so we can import catalog.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from modules.map.catalog import MAP_REGIONS
from wrolpi.scripts.build_map_search import build_search_index

SPARQL_URL = 'https://query.wikidata.org/sparql'
SPARQL_BATCH_SIZE = 2000
SPARQL_DELAY = 2  # seconds between batches

DEFAULT_CDN_BASE = 'https://wrolpi.nyc3.cdn.digitaloceanspaces.com/maps'


def format_size(size_bytes: int) -> str:
    if size_bytes >= 1_000_000_000:
        return f'{size_bytes / 1_000_000_000:.1f} GB'
    elif size_bytes >= 1_000_000:
        return f'{size_bytes / 1_000_000:.1f} MB'
    elif size_bytes >= 1_000:
        return f'{size_bytes / 1_000:.1f} kB'
    return f'{size_bytes} B'


def sha256_file(file_path: str) -> str:
    """Compute SHA-256 hash of a file using chunked reading (safe for multi-GB files)."""
    h = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def sign_hash(sha256_hex: str) -> str:
    """GPG-sign a SHA-256 hash string, return armored detached signature."""
    result = subprocess.run(
        ['gpg', '--batch', '-u', 'roland@learningselfreliance.com', '--detach-sign', '--armor'],
        input=sha256_hex.encode(), capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f'GPG signing failed: {result.stderr.decode().strip()}')
    return result.stdout.decode()


def generate_meta4(name: str, url: str, sha256: str, size: int, signature: str) -> str:
    """Generate Metalink4 XML with hash, size, url, and GPG signature of the hash."""
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<metalink xmlns="urn:ietf:params:xml:ns:metalink">\n'
        f'  <file name="{name}">\n'
        f'    <size>{size}</size>\n'
        f'    <hash type="sha-256">{sha256}</hash>\n'
        f'    <signature mediatype="application/pgp-signature">{signature}</signature>\n'
        f'    <url>{url}</url>\n'
        f'  </file>\n'
        f'</metalink>\n'
    )


def write_meta4(file_path: str, cdn_url: str):
    """Compute hash, sign it, and write a signed .meta4 file alongside the given file."""
    name = os.path.basename(file_path)
    size = os.path.getsize(file_path)
    sha256 = sha256_file(file_path)
    print(f'  Signing hash for {name}...')
    signature = sign_hash(sha256)
    meta4_xml = generate_meta4(name, cdn_url, sha256, size, signature)
    meta4_path = f'{file_path}.meta4'
    with open(meta4_path, 'w') as f:
        f.write(meta4_xml)
    print(f'  Written {os.path.basename(meta4_path)}')


def extract_region(planet_path: str, output_path: str, bbox: str, threads: int = 4) -> bool:
    """Run pmtiles extract for a single region. Returns True on success."""
    cmd = ['pmtiles', 'extract', planet_path, output_path, f'--bbox={bbox}',
           f'--download-threads={threads}']
    print(f'  Running: {" ".join(cmd)}')
    result = subprocess.run(cmd, capture_output=False)
    return result.returncode == 0


def enrich_search_db_with_regions(search_db_path):
    """Query Wikidata SPARQL to look up the administrative region for each place and update the search.db.

    Batches queries in chunks of SPARQL_BATCH_SIZE to stay within Wikidata's 60s timeout.
    """
    conn = sqlite3.connect(str(search_db_path))
    conn.row_factory = sqlite3.Row

    # Collect all wikidata IDs that need enrichment.
    rows = conn.execute("SELECT id, wikidata FROM places WHERE wikidata != '' AND wikidata IS NOT NULL").fetchall()
    qids = {row['wikidata']: row['id'] for row in rows if row['wikidata']}

    if not qids:
        print(f'  No wikidata IDs to enrich in {search_db_path}')
        conn.close()
        return

    print(f'  Enriching {len(qids)} places with Wikidata regions...', flush=True)

    # Batch SPARQL queries.
    qid_list = list(qids.keys())
    region_map = {}  # qid -> region label

    for i in range(0, len(qid_list), SPARQL_BATCH_SIZE):
        batch = qid_list[i:i + SPARQL_BATCH_SIZE]
        batch_num = i // SPARQL_BATCH_SIZE + 1
        total_batches = (len(qid_list) + SPARQL_BATCH_SIZE - 1) // SPARQL_BATCH_SIZE
        print(f'    SPARQL batch {batch_num}/{total_batches} ({len(batch)} IDs)...', flush=True)

        values = ' '.join(f'wd:{qid}' for qid in batch)
        # Get direct P131 (often county) and its parent P131 (often state).
        # Use the parent when available to get the state/province level.
        sparql = f"""
        SELECT ?entity ?regionLabel ?parentLabel WHERE {{
          VALUES ?entity {{ {values} }}
          ?entity wdt:P131 ?region .
          OPTIONAL {{ ?region wdt:P131 ?parent . }}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" . }}
        }}
        """

        try:
            resp = requests.post(
                SPARQL_URL,
                data={'query': sparql, 'format': 'json'},
                headers={'User-Agent': 'WROLPi/1.0 (https://wrolpi.org)'},
                timeout=90,
            )
            resp.raise_for_status()
            bindings = resp.json().get('results', {}).get('bindings', [])

            # Substrings that indicate a county-level region (use parent instead).
            county_indicators = ('county', 'parish', 'borough', 'municipality',
                                 'district', 'canton', 'comarca', 'département',
                                 'united counties')

            for b in bindings:
                entity_uri = b.get('entity', {}).get('value', '')
                qid = entity_uri.rsplit('/', 1)[-1] if entity_uri else ''
                parent_label = b.get('parentLabel', {}).get('value', '')
                region_label = b.get('regionLabel', {}).get('value', '')

                # Default to the direct P131 region (usually state or province).
                # If it looks like a county, use the parent (state) instead.
                if region_label and any(ind in region_label.lower() for ind in county_indicators):
                    best_label = parent_label or region_label
                else:
                    best_label = region_label or parent_label

                if qid and best_label and qid not in region_map:
                    region_map[qid] = best_label

            print(f'    Got {len(bindings)} results', flush=True)
        except Exception as e:
            print(f'    WARNING: SPARQL batch failed: {e}', flush=True)

        if i + SPARQL_BATCH_SIZE < len(qid_list):
            time.sleep(SPARQL_DELAY)

    # Update the search.db with region labels.
    updated = 0
    for qid, region_label in region_map.items():
        if qid in qids:
            conn.execute('UPDATE places SET region = ? WHERE wikidata = ?', (region_label, qid))
            updated += 1

    conn.commit()
    conn.close()
    print(f'  Enriched {updated}/{len(qids)} places with region names', flush=True)


def main():
    parser = argparse.ArgumentParser(description='Extract map regions and generate CDN manifest.')
    parser.add_argument('planet', help='Path to the planet PMTiles file')
    parser.add_argument('version', help='Version string (e.g. 20260329)')
    parser.add_argument('output_dir', help='Output directory for extracted files and manifest')
    parser.add_argument('--cdn-base', default=DEFAULT_CDN_BASE,
                        help=f'CDN base URL (default: {DEFAULT_CDN_BASE})')
    parser.add_argument('--threads', type=int, default=4,
                        help='Download threads for pmtiles extract (default: 4)')
    args = parser.parse_args()

    planet_path = os.path.abspath(args.planet)
    output_dir = os.path.abspath(args.output_dir)
    cdn_base = args.cdn_base.rstrip('/')

    if not os.path.isfile(planet_path):
        print(f'Error: Planet file not found: {planet_path}')
        sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)

    # Separate regions by type.
    bbox_regions = []
    terrain_region = None

    for r in MAP_REGIONS:
        if r.get('terrain'):
            terrain_region = r
        elif r.get('bbox'):
            bbox_regions.append(r)

    print(f'Planet file: {planet_path}')
    print(f'Version: {args.version}')
    print(f'Output dir: {output_dir}')
    print(f'CDN base: {cdn_base}')
    print(f'Regions to extract: {len(bbox_regions)}')
    print()

    # Extract each bbox region.
    manifest_regions = {}
    search_index_urls = {}
    results = []
    failed = []

    for i, r in enumerate(bbox_regions, 1):
        region = r['region']
        bbox = r['bbox']
        output_name = f'{region}-{args.version}.pmtiles'
        output_path = os.path.join(output_dir, output_name)

        print(f'[{i}/{len(bbox_regions)}] Extracting {r["name"]} ({region})...')

        if os.path.isfile(output_path):
            size = os.path.getsize(output_path)
            print(f'  Already exists ({format_size(size)}), skipping.')
        else:
            start = time.time()
            success = extract_region(planet_path, output_path, bbox, threads=args.threads)
            elapsed = time.time() - start

            if not success:
                print(f'  FAILED after {elapsed:.0f}s')
                failed.append(region)
                continue

            size = os.path.getsize(output_path)
            print(f'  Done in {elapsed:.0f}s ({format_size(size)})')

        size = os.path.getsize(output_path)
        cdn_url = f'{cdn_base}/{output_name}'
        write_meta4(output_path, cdn_url)
        results.append((r['name'], region, size))
        manifest_regions[region] = cdn_url

        # Build search index for this region, then enrich with Wikidata region names.
        search_db_path = build_search_index(output_path)
        if search_db_path:
            enrich_search_db_with_regions(search_db_path)
            search_db_name = os.path.basename(str(search_db_path))
            search_cdn_url = f'{cdn_base}/{search_db_name}'
            write_meta4(str(search_db_path), search_cdn_url)
            search_index_urls[region] = search_cdn_url

    # Add terrain to manifest if the file exists in output_dir.
    if terrain_region:
        terrain_name = f'{terrain_region["region"]}.pmtiles'
        terrain_path = os.path.join(output_dir, terrain_name)
        if os.path.isfile(terrain_path):
            cdn_url = f'{cdn_base}/{terrain_name}'
            write_meta4(terrain_path, cdn_url)
            manifest_regions[terrain_region['region']] = cdn_url
            size = os.path.getsize(terrain_path)
            results.append((terrain_region['name'], terrain_region['region'], size))
            print(f'Terrain file found: {terrain_name} ({format_size(size)})')
        else:
            print(f'Warning: Terrain file not found at {terrain_path} — not included in manifest.')

    # Build manifest.
    manifest = {
        'version': args.version,
        'regions': manifest_regions,
    }
    # Add terrain URL if present.
    if terrain_region and terrain_region['region'] in manifest_regions:
        manifest['terrain_url'] = manifest_regions[terrain_region['region']]
    # Add search index URLs.
    if search_index_urls:
        manifest['search_indexes'] = search_index_urls

    manifest_path = os.path.join(output_dir, 'manifest.json')
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)
    print(f'\nManifest written to: {manifest_path}')

    # Sign manifest with GPG.
    sig_path = f'{manifest_path}.sig'
    print(f'Signing manifest...')
    result = subprocess.run(
        ['gpg', '-u', 'roland@learningselfreliance.com', '--detach-sign', '--armor', '-o', sig_path, manifest_path],
        capture_output=True,
    )
    if result.returncode == 0:
        print(f'Signature written to: {sig_path}')
    else:
        print(f'ERROR: GPG signing failed: {result.stderr.decode().strip()}')
        print(f'Sign manually and re-run, or fix GPG key access:'
              f'\n  gpg -u roland@learningselfreliance.com --detach-sign --armor -o {sig_path} {manifest_path}')
        sys.exit(1)

    # Print summary.
    print(f'\n{"="*70}')
    print(f'{"Region":<45} {"Size":>12}')
    print(f'{"-"*45} {"-"*12}')
    total_size = 0
    for name, region, size in results:
        print(f'{name:<45} {format_size(size):>12}')
        total_size += size
    print(f'{"-"*45} {"-"*12}')
    print(f'{"Total":<45} {format_size(total_size):>12}')
    print(f'{"="*70}')

    if failed:
        print(f'\nFailed regions ({len(failed)}): {", ".join(failed)}')
        sys.exit(1)

    print(f'\nAll {len(bbox_regions)} regions extracted successfully.')
    print(f'Upload contents of {output_dir} to {cdn_base}')


if __name__ == '__main__':
    main()
