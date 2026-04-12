import asyncio
import contextlib
import math
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import List

from modules.map.lib import get_map_directory
from wrolpi.common import logger, background_task
from wrolpi.events import Events
from wrolpi.flags import map_search_building

logger = logger.getChild(__name__)

BUILD_SCRIPT = Path(__file__).parent.parent.parent / 'wrolpi' / 'scripts' / 'build_map_search.py'


def get_search_db_files() -> List[Path]:
    """Find all .search.db files in the map directory."""
    map_directory = get_map_directory()
    return sorted(map_directory.glob('*.search.db'))


def search_places(query: str, limit: int = 12, offset: int = 0, lat: float = None, lon: float = None) -> dict:
    """Search all .search.db files for places matching the query.

    Results are ranked by importance (min_zoom) and optionally by proximity to lat/lon.
    Returns {"results": [...], "total": N}.
    """
    db_files = get_search_db_files()
    if not db_files:
        return {'results': [], 'total': 0}

    results = []

    # Cap the number of rows fetched per DB to bound memory on large regional indexes
    # (e.g. a prefix query like "S*" can match hundreds of thousands of rows).  The
    # cap is a multiple of (offset + limit) to keep enough headroom for ranking and
    # cross-DB deduplication before pagination.
    per_db_cap = max((offset + limit) * 5, 100)

    # FTS5 match query with prefix matching.  Escape embedded double quotes.
    escaped = query.replace('"', '""')
    fts_query = f'"{escaped}"*'

    for db_path in db_files:
        try:
            with contextlib.closing(sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)) as conn:
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
                """, (fts_query, per_db_cap)).fetchall()

                for row in rows:
                    result = dict(row)
                    if lat is not None and lon is not None:
                        dlat = result['lat'] - lat
                        dlon = result['lon'] - lon
                        result['distance'] = math.sqrt(dlat ** 2 + dlon ** 2)
                    results.append(result)
        except sqlite3.OperationalError as e:
            logger.warning(f'Search error in {db_path.name}: {e}')
            continue

    # Fuzzy fallback: if FTS5 found nothing, try LIKE substring matching.
    if not results:
        like_pattern = f'%{query}%'
        for db_path in db_files:
            try:
                with contextlib.closing(sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)) as conn:
                    conn.row_factory = sqlite3.Row

                    rows = conn.execute("""
                        SELECT p.name, p.kind, p.lat, p.lon, p.min_zoom, p.source,
                               p.kind_detail, p.population, p.region, 0 AS fts_rank
                        FROM places p
                        WHERE p.name LIKE ?
                        ORDER BY p.min_zoom, p.population DESC
                        LIMIT ?
                    """, (like_pattern, per_db_cap)).fetchall()

                    for row in rows:
                        result = dict(row)
                        if lat is not None and lon is not None:
                            dlat = result['lat'] - lat
                            dlon = result['lon'] - lon
                            result['distance'] = math.sqrt(dlat ** 2 + dlon ** 2)
                        results.append(result)
            except sqlite3.OperationalError as e:
                logger.warning(f'LIKE search error in {db_path.name}: {e}')
                continue

    # Sort by importance (lower min_zoom = more important), then by proximity or FTS rank.
    # Coerce NULL min_zoom (possible from older schemas) to a default; `dict.get` returns
    # None rather than the default for explicit NULL values.
    if lat is not None and lon is not None:
        results.sort(key=lambda r: (r.get('min_zoom') or 10, r.get('distance') or 0))
    else:
        results.sort(key=lambda r: (r.get('min_zoom') or 10, r.get('fts_rank') or 0))

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

    # Use the DB-wide count for `total` so pagination isn't capped by `per_db_cap`.
    # Fall back to the deduped length if the count query fails (e.g. the per-DB cap
    # was never hit, in which case they agree anyway).
    if len(results) >= per_db_cap:
        total = search_places_count(query)
    else:
        total = len(deduped)

    # Remove internal ranking fields before returning.
    final = []
    for r in deduped[offset:offset + limit]:
        r.pop('fts_rank', None)
        r.pop('distance', None)
        final.append(r)

    return {'results': final, 'total': total}


def search_places_count(query: str) -> int:
    """Return the count of places matching the query across all search indexes."""
    db_files = get_search_db_files()
    if not db_files:
        return 0

    escaped = query.replace('"', '""')
    fts_query = f'"{escaped}"*'
    total = 0

    for db_path in db_files:
        try:
            with contextlib.closing(sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)) as conn:
                row = conn.execute("""
                    SELECT COUNT(*) FROM places_fts WHERE places_fts MATCH ?
                """, (fts_query,)).fetchone()
                total += row[0] if row else 0
        except sqlite3.OperationalError:
            continue

    # LIKE fallback count if FTS5 found nothing.
    if total == 0:
        like_pattern = f'%{query}%'
        for db_path in db_files:
            try:
                with contextlib.closing(sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)) as conn:
                    row = conn.execute("SELECT COUNT(*) FROM places WHERE name LIKE ?",
                                       (like_pattern,)).fetchone()
                    total += row[0] if row else 0
            except sqlite3.OperationalError:
                continue

    return total


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


def _check_tippecanoe() -> bool:
    """Return True if tippecanoe-decode is on PATH. If missing, log and send an Event."""
    if shutil.which('tippecanoe-decode'):
        return True
    msg = 'tippecanoe-decode not found on PATH — map search index cannot be built'
    logger.error(msg)
    Events.send_tippecanoe_missing(msg)
    return False


def _should_enrich() -> bool:
    """Return True if Wikidata enrichment should be attempted (WROL mode is not active)."""
    try:
        from wrolpi.common import get_wrolpi_config
        return not get_wrolpi_config().wrol_mode
    except Exception:
        return False


async def _run_build(cmd: list, description: str):
    """Run a build subprocess with the map_search_building flag set.

    The flag is automatically cleared when the build finishes (success or failure).
    """
    with map_search_building:
        logger.warning(f'Starting search index build: {description}')
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await proc.communicate()
        output = stdout.decode()[-500:] if stdout else ''
        if proc.returncode == 0:
            logger.warning(f'Search index build completed: {description}')
            Events.send_map_search_complete(f'Search index built for {description}')
        else:
            logger.error(f'Search index build failed for {description} (exit {proc.returncode}):\n{output}')
            Events.send_map_search_failed(f'Search index build failed for {description}')


def rebuild_search_index(pmtiles_name: str, max_zoom: int = 10) -> bool:
    """Launch the build script as a background task for a single PMTiles file.

    Returns True if the build was started, False if the file doesn't exist.
    """
    map_directory = get_map_directory()
    pmtiles_path = (map_directory / pmtiles_name).resolve()

    if not pmtiles_path.is_relative_to(map_directory.resolve()):
        raise ValueError(f'Invalid filename: {pmtiles_name}')

    if not pmtiles_path.is_file():
        return False

    if map_search_building.is_set():
        logger.warning(f'Search index build already running — ignoring request for {pmtiles_name}')
        return False

    if not _check_tippecanoe():
        return False

    cmd = [sys.executable, str(BUILD_SCRIPT), str(pmtiles_path), '--max-zoom', str(max_zoom)]
    if _should_enrich():
        cmd.append('--enrich')

    background_task(_run_build(cmd, pmtiles_name))
    return True


def rebuild_all_search_indexes(max_zoom: int = 10) -> bool:
    """Launch the build script for the entire map directory as a background task."""
    map_directory = get_map_directory()

    if not any(map_directory.glob('*.pmtiles')):
        return False

    if map_search_building.is_set():
        logger.warning('Search index build already running — ignoring rebuild-all request')
        return False

    if not _check_tippecanoe():
        return False

    cmd = [sys.executable, str(BUILD_SCRIPT), str(map_directory), '--max-zoom', str(max_zoom)]
    if _should_enrich():
        cmd.append('--enrich')

    background_task(_run_build(cmd, 'all map files'))
    return True


