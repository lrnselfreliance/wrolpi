import pathlib
from abc import ABC
from collections import defaultdict
from typing import List, Type, Tuple
from zipfile import ZipFile

from wrolpi.vars import PYTEST, FILE_MAX_TEXT_SIZE

try:
    from PyPDF2 import PdfReader
except ImportError:
    PdfReader = None

from wrolpi.common import logger, split_lines_by_length, truncate_object_bytes

logger = logger.getChild(__name__)

__all__ = ['Indexer', 'DefaultIndexer', 'ZipIndexer', 'TextIndexer', 'find_indexer', 'register_indexer']


class Indexer(object):

    @staticmethod
    def get_title(path: pathlib.Path):
        from wrolpi.files.lib import split_file_name_words
        words = split_file_name_words(path.name)
        return words

    @classmethod
    def create_index(cls, path: pathlib.Path) -> Tuple:
        # All files can have their title as the highest priority search.
        a = cls.get_title(path)
        return a, None, None, None


class DefaultIndexer(Indexer, ABC):
    """If this Indexer is used, it is because we could not match the file to a more specific Indexer."""
    pass


indexer_map = defaultdict(lambda: DefaultIndexer)


def find_indexer(mimetype: str) -> Type[Indexer]:
    """Find the Indexer for a given File model."""
    if not mimetype:
        return DefaultIndexer

    # Get the indexer that matches the mimetype of this file.
    indexer = next((v for k, v in indexer_map.items() if mimetype.startswith(k)), None)

    if not indexer:
        # Use the broad indexer.
        indexer = indexer_map[mimetype.split('/')[0]]

    return indexer


def register_indexer(*mimetypes: str):
    """Register an Indexer for a file mimetype."""

    def wrapper(indexer: Indexer):
        for mimetype in mimetypes:
            if mimetype in indexer_map:
                raise KeyError(f'Cannot register indexer.  {mimetype} is already registered.')

            indexer_map[mimetype] = indexer
        return indexer

    return wrapper


@register_indexer('application/zip')
class ZipIndexer(Indexer, ABC):
    """Handles archive files like zip."""

    @classmethod
    def create_index(cls, path: pathlib.Path):
        a = cls.get_title(path)
        file_names = cls.get_file_names(path)
        return a, None, None, file_names

    @classmethod
    def get_file_names(cls, path: pathlib.Path) -> List[str]:
        """Return all the names of the files in the zip file."""
        from wrolpi.files.lib import split_file_name_words
        try:
            with ZipFile(path, 'r') as zip_:
                file_names = ' '.join([split_file_name_words(pathlib.Path(name).name) for name in zip_.namelist()])
                file_names = truncate_object_bytes(file_names, FILE_MAX_TEXT_SIZE)
                return file_names
        except Exception as e:
            logger.error(f'Unable to get information from zip: {path}', exc_info=e)
            if PYTEST:
                raise


@register_indexer('text/plain')
class TextIndexer(Indexer, ABC):
    """Handles plain text files.

    Detects VTT (caption) files and forwards them on."""

    @classmethod
    def create_index(cls, path: pathlib.Path):
        a = cls.get_title(path)
        words = cls.get_words(path)
        return a, None, None, words

    @staticmethod
    def get_words(path: pathlib.Path) -> str:
        """Read the words from a file."""
        # TODO this only supports English.
        contents = path.read_text()
        contents = truncate_object_bytes(contents, FILE_MAX_TEXT_SIZE)
        words = split_lines_by_length(contents)
        return words
