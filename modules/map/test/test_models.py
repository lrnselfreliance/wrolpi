from pathlib import Path

import pytest

from modules.map import models


@pytest.mark.parametrize('size,expected', [
    (0, 0),
    (-1, 0),
    (17737381, 4498),
    (63434267, 16087),
    (87745484, 22253),
    (136372996, 34586),
    (116318111, 29499),
])
def test_seconds_to_import_rpi4(size, expected):
    assert models.seconds_to_import(Path('file.osm.pbf'), size) == expected
