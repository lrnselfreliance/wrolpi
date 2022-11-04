from pathlib import Path

import pytest

from modules.map import models


@pytest.mark.parametrize('path,size,expected', [
    ('file.osm.pbf', 0, 0),
    ('file.osm.pbf', -1, 0),
    ('file.osm.pbf', 17737381, 2342),
    ('file.osm.pbf', 63434267, 8376),
    ('file.osm.pbf', 87745484, 11586),
    ('file.osm.pbf', 136372996, 18007),
    ('file.osm.pbf', 116318111, 15359),
])
def test_seconds_to_import_rpi4(path, size, expected):
    assert models.seconds_to_import(Path(path), size) == expected
