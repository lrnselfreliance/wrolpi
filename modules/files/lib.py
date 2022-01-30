from pathlib import Path
from typing import List

from wrolpi.common import get_media_directory, wrol_mode_check
from wrolpi.errors import InvalidFile


def filter_parent_directories(directories: List[Path]) -> List[Path]:
    """
    Remove parent directories if their children are in the list.

    >>> filter_parent_directories([Path('foo'), Path('foo/bar'), Path('baz')])
    [Path('foo/bar'), Path('baz')]
    """
    unique_children = set()
    for directory in sorted(directories):
        for parent in directory.parents:
            # Remove any parent of this child.
            if parent in unique_children:
                unique_children.remove(parent)
        unique_children.add(directory)

    # Restore the original order.
    new_directories = [i for i in directories if i in unique_children]
    return new_directories


def list_files(directories: List[str]) -> List[Path]:
    """
    List all files down to the directories provided.  This includes all parent directories of the directories.
    """
    media_directory = get_media_directory()

    # Always display the media_directory files.
    paths = list(media_directory.iterdir())

    if directories:
        directories = [media_directory / i for i in directories if i]
        directories = filter_parent_directories(directories)
        for directory in directories:
            directory = media_directory / directory
            for parent in directory.parents:
                is_relative_to = str(media_directory).startswith(str(parent))
                if parent == Path('.') or is_relative_to:
                    continue
                paths.extend(parent.iterdir())
            paths.extend(directory.iterdir())

    return paths


@wrol_mode_check
def delete_file(file: str):
    """Delete a file in the media directory."""
    file = get_media_directory() / file
    if file.is_dir() or not file.is_file():
        raise InvalidFile(f'Invalid file {file}')
    file.unlink()
