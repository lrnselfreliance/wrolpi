import math
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from modules.map.lib import get_map_directory
from wrolpi.common import logger

logger = logger.getChild(__name__)

BUILD_SCRIPT = Path(__file__).parent.parent.parent / 'wrolpi' / 'scripts' / 'build_map_search.py'


def get_search_db_files() -> List[Path]:
    """Find all .search.db files in the map directory."""
    map_directory = get_map_directory()
    return sorted(map_directory.glob('*.search.db'))


def search_places(query: str, limit: int = 10, lat: float = None, lon: float = None) -> List[dict]:
    """Search all .search.db files for places matching the query.

    Results are ranked by importance (min_zoom) and optionally by proximity to lat/lon.
    """
    db_files = get_search_db_files()
    if not db_files:
        return []

    results = []

    # FTS5 match query with prefix matching.
    fts_query = f'"{query}"*'

    for db_path in db_files:
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row

            rows = conn.execute("""
                SELECT p.name, p.kind, p.lat, p.lon, p.min_zoom, p.source,
                       p.kind_detail, p.population, p.region,
                       places_fts.rank AS fts_rank
                FROM places_fts
                JOIN places p ON p.id = places_fts.rowid
                WHERE places_fts MATCH ?
                ORDER BY places_fts.rank
                LIMIT ?
            """, (fts_query, limit * 3)).fetchall()

            for row in rows:
                result = dict(row)
                if lat is not None and lon is not None:
                    dlat = result['lat'] - lat
                    dlon = result['lon'] - lon
                    result['distance'] = math.sqrt(dlat ** 2 + dlon ** 2)
                results.append(result)

            conn.close()
        except sqlite3.OperationalError as e:
            logger.warning(f'Search error in {db_path.name}: {e}')
            continue

    # Sort by importance (lower min_zoom = more important), then by proximity or FTS rank.
    if lat is not None and lon is not None:
        results.sort(key=lambda r: (r.get('min_zoom', 10), r['distance']))
    else:
        results.sort(key=lambda r: (r.get('min_zoom', 10), r['fts_rank']))

    # Deduplicate across sources: same name+kind at ~same location keeps highest population.
    seen = {}
    deduped = []
    for r in results:
        key = (r['name'], r['kind'], round(r['lat'], 2), round(r['lon'], 2))
        if key not in seen:
            seen[key] = len(deduped)
            deduped.append(r)
        else:
            # Keep the entry with higher population.
            existing = deduped[seen[key]]
            if (r.get('population') or 0) > (existing.get('population') or 0):
                deduped[seen[key]] = r

    # Remove internal ranking fields before returning.
    final = []
    for r in deduped[:limit]:
        r.pop('fts_rank', None)
        r.pop('distance', None)
        final.append(r)

    return final


def get_search_status() -> dict:
    """Return status of search indexes: which PMTiles files have indexes and which don't."""
    map_directory = get_map_directory()

    pmtiles_files = sorted(map_directory.glob('*.pmtiles'))
    # Strip the double .search.db extension to get the PMTiles stem.
    search_db_files = {p.name.removesuffix('.search.db') for p in get_search_db_files()}

    indexed = []
    missing = []

    for pmtiles_path in pmtiles_files:
        info = {'name': pmtiles_path.name, 'stem': pmtiles_path.stem}
        if pmtiles_path.stem in search_db_files:
            db_path = pmtiles_path.with_suffix('.search.db')
            info['search_db_size'] = db_path.stat().st_size
            indexed.append(info)
        else:
            missing.append(info)

    return {
        'indexed': indexed,
        'missing': missing,
    }


def rebuild_search_index(pmtiles_name: str, max_zoom: int = 10) -> Optional[subprocess.Popen]:
    """Launch the build script as a background subprocess for a single PMTiles file.

    Returns the Popen object, or None if the file doesn't exist.
    """
    map_directory = get_map_directory()
    pmtiles_path = (map_directory / pmtiles_name).resolve()

    if not pmtiles_path.is_relative_to(map_directory.resolve()):
        raise ValueError(f'Invalid filename: {pmtiles_name}')

    if not pmtiles_path.is_file():
        return None

    logger.warning(f'Launching search index build for {pmtiles_name}')
    proc = subprocess.Popen(
        [sys.executable, str(BUILD_SCRIPT), str(pmtiles_path), '--max-zoom', str(max_zoom)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    return proc


def rebuild_all_search_indexes(max_zoom: int = 10) -> Optional[subprocess.Popen]:
    """Launch the build script for the entire map directory as a background subprocess."""
    map_directory = get_map_directory()

    logger.warning(f'Launching search index build for all files in {map_directory}')
    proc = subprocess.Popen(
        [sys.executable, str(BUILD_SCRIPT), str(map_directory), '--max-zoom', str(max_zoom)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    return proc


def delete_search_db(pmtiles_name: str) -> bool:
    """Delete the .search.db companion for a PMTiles file. Returns True if deleted."""
    map_directory = get_map_directory()
    stem = Path(pmtiles_name).stem
    search_db_path = map_directory / f'{stem}.search.db'
    if search_db_path.is_file():
        search_db_path.unlink()
        logger.warning(f'Deleted search index: {search_db_path}')
        return True
    return False
