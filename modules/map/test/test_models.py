import pytest

from modules.map import models


@pytest.mark.parametrize('size,expected', [
    (0, 0),
    (-1, 0),
    (17737381, 4475),
    (63434267, 16006),
    (87745484, 22141),
    (136372996, 34411),
    (116318111, 29351),
])
def test_seconds_to_import_rpi4(size, expected):
    assert models.seconds_to_import(size) == expected
