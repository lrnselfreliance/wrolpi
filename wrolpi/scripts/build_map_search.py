#!/usr/bin/env python3
"""Build SQLite FTS5 search indexes from PMTiles vector tile files.

Uses tippecanoe-decode (C++) to extract place names and POIs from the `places`
and `pois` layers in Protomaps basemap PMTiles files, then writes them into a
SQLite FTS5 database for fast offline search.

Usage:
    # Build index for a single file:
    python scripts/build_map_search.py test/map/usa.pmtiles

    # Build indexes for all .pmtiles files in a directory:
    python scripts/build_map_search.py test/map/

    # Customize max zoom (default 10, higher = more POIs but slower):
    python scripts/build_map_search.py test/map/usa.pmtiles --max-zoom 12

Requirements:
    - tippecanoe-decode (part of felt/tippecanoe) installed and on PATH
"""
import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Layers in the Protomaps basemap that contain searchable features.
SEARCHABLE_LAYERS = {'places', 'pois'}

MIN_ZOOM = 2
DEFAULT_MAX_ZOOM = 10

# Planet files are too large to process — they should use regional extracts instead.
PLANET_RE = re.compile(r'^\d{8}$')


def is_planet_file(name):
    """Detect full planet files: 'planet-*.pmtiles' or bare date like '20260329.pmtiles'."""
    stem = Path(name).stem if '.' in name else name
    return stem.startswith('planet-') or bool(PLANET_RE.match(stem))


def extract_features(pmtiles_path, source_name, min_zoom, max_zoom):
    """Extract place/POI features from a PMTiles file using tippecanoe-decode.

    Returns a list of (name, kind, lat, lon, min_zoom, source, kind_detail, population, wikidata) tuples.
    """
    layers_args = []
    for layer in sorted(SEARCHABLE_LAYERS):
        layers_args.extend(['-l', layer])

    cmd = [
        'tippecanoe-decode',
        *layers_args,
        '-Z', str(min_zoom),
        '-z', str(max_zoom),
        str(pmtiles_path),
    ]

    print(f'  Running: {" ".join(cmd)}', flush=True)
    t0 = time.time()

    # Stream tippecanoe-decode stdout to a temp file instead of capturing into RAM.
    # The decoded GeoJSON for regional PMTiles can reach hundreds of MB, which would
    # exhaust memory on a Raspberry Pi if held as a Python string alongside the
    # parsed dict (see PR #405 review).
    tmp_fd, tmp_path = tempfile.mkstemp(suffix='.json', prefix='tippecanoe-decode-')
    try:
        with os.fdopen(tmp_fd, 'w') as out:
            result = subprocess.run(cmd, stdout=out, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            raise RuntimeError(f'tippecanoe-decode failed: {result.stderr.strip()}')

        elapsed = time.time() - t0
        print(f'  tippecanoe-decode completed in {elapsed:.1f}s', flush=True)

        # Parse the nested GeoJSON output.
        # Structure: FeatureCollection > tile FeatureCollections > layer FeatureCollections > features.
        t0 = time.time()
        with open(tmp_path) as f:
            fc = json.load(f)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    seen = set()
    features = []

    for tile_fc in fc.get('features', []):
        for layer_fc in tile_fc.get('features', []):
            layer_name = layer_fc.get('properties', {}).get('layer', '')
            if layer_name not in SEARCHABLE_LAYERS:
                continue

            for feature in layer_fc.get('features', []):
                props = feature.get('properties', {})
                name = props.get('name')
                if not name:
                    continue

                geom = feature.get('geometry', {})
                coords = geom.get('coordinates')
                if not coords:
                    continue

                kind = props.get('kind', layer_name)
                kind_detail = props.get('kind_detail', '')
                population = props.get('population')
                wikidata = props.get('wikidata', '')
                min_z = props.get('min_zoom', 0)

                # tippecanoe-decode outputs [lon, lat] in real coordinates.
                geom_type = geom.get('type')
                if geom_type == 'Point':
                    lon, lat = coords[0], coords[1]
                elif geom_type == 'MultiPoint' and coords:
                    lon, lat = coords[0][0], coords[0][1]
                elif geom_type == 'Polygon' and coords and coords[0]:
                    ring = coords[0]
                    lon = sum(c[0] for c in ring) / len(ring)
                    lat = sum(c[1] for c in ring) / len(ring)
                else:
                    continue

                lat = round(lat, 6)
                lon = round(lon, 6)

                # Deduplicate: same name+kind within ~1.1km collapses to one entry.
                # When a duplicate is found, keep the one with higher population (more data).
                key = (name, kind, round(lat, 2), round(lon, 2))
                if key not in seen:
                    seen.add(key)
                    features.append((name, kind, lat, lon, min_z, source_name, kind_detail, population, wikidata))

    elapsed = time.time() - t0
    print(f'  Parsed {len(features)} unique features ({elapsed:.1f}s)', flush=True)
    return features


def write_search_db(features, output_path):
    """Write features to a SQLite FTS5 database."""
    conn = sqlite3.connect(str(output_path))
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute("""
        CREATE TABLE places (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            kind TEXT,
            lat REAL NOT NULL,
            lon REAL NOT NULL,
            min_zoom REAL,
            source TEXT,
            kind_detail TEXT,
            population INTEGER,
            wikidata TEXT,
            region TEXT
        )
    """)
    conn.execute("""
        CREATE VIRTUAL TABLE places_fts USING fts5(
            name, kind, content=places, content_rowid=id
        )
    """)

    conn.executemany(
        'INSERT INTO places (name, kind, lat, lon, min_zoom, source, kind_detail, population, wikidata)'
        ' VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
        features,
    )
    conn.execute("INSERT INTO places_fts(places_fts) VALUES('rebuild')")
    conn.commit()
    conn.close()


def build_search_index(pmtiles_path, output_path=None, max_zoom=DEFAULT_MAX_ZOOM):
    """Build a search index for a single PMTiles file.

    Returns the output path on success, or None on failure.
    """
    pmtiles_path = Path(pmtiles_path).resolve()

    if is_planet_file(pmtiles_path.name):
        print(f'Skipping planet file {pmtiles_path.name} — use regional extracts instead.', flush=True)
        return None

    if output_path is None:
        output_path = pmtiles_path.with_suffix('.search.db')
    else:
        output_path = Path(output_path).resolve()

    source_name = pmtiles_path.stem

    print(f'Building search index for {pmtiles_path.name}...', flush=True)
    print(f'  Output: {output_path}', flush=True)
    print(f'  Zoom range: z{MIN_ZOOM}-z{max_zoom}', flush=True)

    if output_path.exists():
        print(f'  Search index already exists, skipping extraction.', flush=True)
        return output_path

    t_start = time.time()

    try:
        features = extract_features(pmtiles_path, source_name, MIN_ZOOM, max_zoom)
    except RuntimeError as e:
        print(f'  ERROR: {e}', flush=True)
        return None

    if not features:
        print(f'  No features found, skipping.', flush=True)
        return None

    write_search_db(features, output_path)

    size_mb = output_path.stat().st_size / (1024 * 1024)
    total_elapsed = time.time() - t_start
    print(f'  Done: {len(features)} features, {size_mb:.1f} MB, {total_elapsed:.1f}s', flush=True)
    return output_path


def build_all_in_directory(directory, max_zoom=DEFAULT_MAX_ZOOM):
    """Build search indexes for all .pmtiles files in a directory.

    Skips terrain files (which contain no place data).
    """
    directory = Path(directory).resolve()
    pmtiles_files = sorted(directory.glob('*.pmtiles'))

    if not pmtiles_files:
        print(f'No .pmtiles files found in {directory}')
        return []

    # Skip terrain and planet files.
    pmtiles_files = [p for p in pmtiles_files
                     if 'terrain' not in p.stem.lower() and not is_planet_file(p.name)]

    print(f'Found {len(pmtiles_files)} PMTiles files in {directory}')
    results = []

    for i, pmtiles_path in enumerate(pmtiles_files, 1):
        print(f'\n[{i}/{len(pmtiles_files)}] {pmtiles_path.name}', flush=True)
        output = build_search_index(pmtiles_path, max_zoom=max_zoom)
        if output:
            results.append(output)

    print(f'\nBuilt {len(results)}/{len(pmtiles_files)} search indexes.')
    return results


def _enrich_results(search_db_paths):
    """Attempt to enrich search databases with Wikidata region names. Fails gracefully."""
    try:
        from wrolpi.scripts.build_map_regions import enrich_search_db_with_regions
    except ImportError:
        print('Warning: could not import enrichment function, skipping.', flush=True)
        return

    for db_path in search_db_paths:
        try:
            enrich_search_db_with_regions(str(db_path))
        except Exception as e:
            print(f'  Warning: enrichment failed for {db_path}: {e}', flush=True)


def main():
    parser = argparse.ArgumentParser(
        description='Build SQLite FTS5 search indexes from PMTiles files.',
    )
    parser.add_argument(
        'path', type=Path,
        help='PMTiles file or directory containing PMTiles files',
    )
    parser.add_argument(
        '--output', type=Path, default=None,
        help='Output .search.db path (only for single file mode)',
    )
    parser.add_argument(
        '--max-zoom', type=int, default=DEFAULT_MAX_ZOOM,
        help=f'Maximum zoom level to scan (default: {DEFAULT_MAX_ZOOM})',
    )
    parser.add_argument(
        '--enrich', action='store_true',
        help='Enrich with Wikidata region names (requires internet)',
    )
    args = parser.parse_args()

    if not shutil.which('tippecanoe-decode'):
        print('Error: tippecanoe-decode not found on PATH.', file=sys.stderr)
        print('Install tippecanoe: https://github.com/felt/tippecanoe', file=sys.stderr)
        sys.exit(1)

    path = args.path.resolve()

    if path.is_dir():
        if args.output:
            print('Error: --output cannot be used with a directory.', file=sys.stderr)
            sys.exit(1)
        results = build_all_in_directory(path, max_zoom=args.max_zoom)
        if args.enrich:
            _enrich_results(results)
    elif path.is_file() and path.suffix == '.pmtiles':
        result = build_search_index(path, output_path=args.output, max_zoom=args.max_zoom)
        if not result:
            sys.exit(1)
        if args.enrich:
            _enrich_results([result])
    else:
        print(f'Error: {path} is not a .pmtiles file or directory.', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
