import sqlite3
from http import HTTPStatus
from pathlib import Path
from unittest import mock

import pytest


def _create_test_search_db(path: Path, features: list):
    """Create a minimal .search.db file with given features for testing."""
    conn = sqlite3.connect(str(path))
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
        'INSERT INTO places (name, kind, lat, lon, min_zoom, source, kind_detail, population, region)'
        ' VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
        features,
    )
    conn.execute("INSERT INTO places_fts(places_fts) VALUES('rebuild')")
    conn.commit()
    conn.close()


@pytest.fixture
def search_db(test_directory):
    """Create a test search database with known features."""
    map_dir = test_directory / 'map'
    map_dir.mkdir(exist_ok=True)

    features = [
        ('Portland', 'locality', 45.5217, -122.6733, 4.0, 'test', 'city', 652503, 'Oregon'),
        ('Portland', 'locality', 43.6559, -70.2576, 5.0, 'test', 'city', 78408, 'Maine'),
        ('San Francisco', 'locality', 37.7881, -122.4097, 3.0, 'test', 'city', 873965, 'California'),
        ('Springfield', 'locality', 39.7990, -89.6436, 6.0, 'test', 'city', 114230, 'Illinois'),
        ('Springfield', 'locality', 37.2085, -93.2918, 6.0, 'test', 'city', 169176, 'Missouri'),
        ('Yellowstone National Park', 'nature_reserve', 44.6222, -110.5616, 8.0, 'test', '', None, None),
    ]
    db_path = map_dir / 'test.search.db'
    _create_test_search_db(db_path, features)
    return db_path


@pytest.mark.asyncio
async def test_search_requires_query(async_client, test_directory):
    """Search endpoint requires a query parameter."""
    request, response = await async_client.get('/api/map/search')
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'error' in response.json


@pytest.mark.asyncio
async def test_search_empty_query(async_client, test_directory):
    """Search endpoint rejects empty query."""
    request, response = await async_client.get('/api/map/search?q=')
    assert response.status_code == HTTPStatus.BAD_REQUEST


@pytest.mark.asyncio
async def test_search_no_indexes(async_client, test_directory):
    """Search returns empty results when no search indexes exist."""
    request, response = await async_client.get('/api/map/search?q=portland')
    assert response.status_code == HTTPStatus.OK
    assert response.json['results'] == []


@pytest.mark.asyncio
async def test_search_returns_results(async_client, test_directory, search_db):
    """Search returns matching results from the index."""
    request, response = await async_client.get('/api/map/search?q=Portland')
    assert response.status_code == HTTPStatus.OK
    results = response.json['results']
    assert len(results) >= 1
    assert results[0]['name'] == 'Portland'
    assert 'lat' in results[0]
    assert 'lon' in results[0]
    assert 'kind' in results[0]


@pytest.mark.asyncio
async def test_search_with_coordinates(async_client, test_directory, search_db):
    """Search with lat/lon returns results sorted by proximity."""
    # Bias toward Portland, OR (45.5, -122.6)
    request, response = await async_client.get('/api/map/search?q=Portland&lat=45.5&lon=-122.6')
    assert response.status_code == HTTPStatus.OK
    results = response.json['results']
    assert len(results) >= 2
    # Portland, OR should be first (closest to bias point).
    assert results[0]['lat'] == pytest.approx(45.5217, abs=0.1)


@pytest.mark.asyncio
async def test_search_prefix_matching(async_client, test_directory, search_db):
    """Search supports prefix matching."""
    request, response = await async_client.get('/api/map/search?q=Spring')
    assert response.status_code == HTTPStatus.OK
    results = response.json['results']
    assert any(r['name'] == 'Springfield' for r in results)


@pytest.mark.asyncio
async def test_search_status_no_files(async_client, test_directory):
    """Status endpoint returns empty when no map files exist."""
    request, response = await async_client.get('/api/map/search/status')
    assert response.status_code == HTTPStatus.OK
    assert response.json['indexed'] == []
    assert response.json['missing'] == []


@pytest.mark.asyncio
async def test_search_status_with_index(async_client, test_directory, search_db, make_files_structure):
    """Status endpoint shows which files have indexes."""
    # Create a PMTiles file that matches the search.db stem.
    make_files_structure(['map/test.pmtiles'])

    request, response = await async_client.get('/api/map/search/status')
    assert response.status_code == HTTPStatus.OK
    assert len(response.json['indexed']) == 1
    assert response.json['indexed'][0]['stem'] == 'test'


@pytest.mark.asyncio
async def test_search_status_missing_index(async_client, test_directory, make_files_structure):
    """Status endpoint shows PMTiles files without search indexes."""
    make_files_structure(['map/usa.pmtiles'])

    request, response = await async_client.get('/api/map/search/status')
    assert response.status_code == HTTPStatus.OK
    assert len(response.json['missing']) == 1
    assert response.json['missing'][0]['stem'] == 'usa'


@pytest.mark.asyncio
async def test_delete_pmtiles_also_deletes_search_db(async_client, test_directory, search_db, make_files_structure):
    """Deleting a PMTiles file also deletes its companion search.db."""
    make_files_structure(['map/test.pmtiles'])

    # Both files exist.
    assert search_db.exists()

    # Delete the PMTiles file.
    request, response = await async_client.delete('/api/map/files/test.pmtiles')
    assert response.status_code == HTTPStatus.NO_CONTENT

    # Search DB should also be deleted.
    assert not search_db.exists()
