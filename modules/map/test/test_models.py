from pathlib import Path

import pytest

from modules.map import models


@pytest.mark.parametrize('path,size,expected', [
    ('file.osm.pbf', 0, 0),
    ('file.osm.pbf', -1, 0),
    ('file.osm.pbf', 17737381, 4498),
    ('file.osm.pbf', 63434267, 16087),
    ('file.osm.pbf', 87745484, 22253),
    ('file.osm.pbf', 136372996, 34586),
    ('file.osm.pbf', 116318111, 29499),
])
def test_seconds_to_import_rpi4(path, size, expected):
    assert models.seconds_to_import(Path(path), size) == expected
