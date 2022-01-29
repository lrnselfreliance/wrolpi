import pathlib
from typing import List

import pytest


@pytest.fixture
def make_files_structure(test_directory):
    def create_files(paths: List[str]) -> List[pathlib.Path]:
        files = []
        for name in paths:
            path = test_directory / name
            if name.endswith('/'):
                path.mkdir()
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            files.append(path)
        return files

    return create_files
