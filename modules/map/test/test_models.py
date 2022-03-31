from pathlib import Path

import pytest

from modules.map import models


@pytest.mark.parametrize('path,size,expected', [
    ('file.osm.pbf', 0, 0),
    ('file.osm.pbf', -1, 0),
    ('file.osm.pbf', 17737381, 4475),
    ('file.osm.pbf', 63434267, 16006),
    ('file.osm.pbf', 87745484, 22141),
    ('file.osm.pbf', 136372996, 34411),
    ('file.osm.pbf', 116318111, 29351),
])
def test_seconds_to_import_rpi4(path, size, expected):
    assert models.seconds_to_import(Path(path), size) == expected
