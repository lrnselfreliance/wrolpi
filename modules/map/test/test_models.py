from pathlib import Path

import pytest

import modules.map.lib
from modules.map import models


@pytest.mark.parametrize('size,expected', [
    (0, 0),
    (-1, 0),
    (17737381, 286),
    (63434267, 1025),
    (87745484, 1418),
    (136372996, 2203),
    (116318111, 1879),
])
def test_seconds_to_import_rpi4(size, expected):
    assert modules.map.lib.seconds_to_import(size) == expected
