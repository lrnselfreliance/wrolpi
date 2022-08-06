import pathlib
import re
from abc import ABC
from collections import defaultdict
from typing import List, Type, Tuple
from zipfile import ZipFile

from wrolpi.common import logger

logger = logger.getChild(__name__)

__all__ = ['Indexer', 'DefaultIndexer', 'ZipIndexer', 'TextIndexer', 'find_indexer', 'register_indexer',
           'MAX_TEXT_FILE_BYTES']


class Indexer(object):

    @staticmethod
    def get_title(file):
        from wrolpi.files.lib import split_path_stem_and_suffix
        path = file.path.path if hasattr(file.path, 'path') else file.path
        return split_path_stem_and_suffix(path)

    @classmethod
    def create_index(cls, file) -> Tuple:
        # All files can have their title as the highest priority search.
        a = cls.get_title(file)
        return a, None, None, None

    @classmethod
    def detect_special_indexer(cls, file):
        return cls


class DefaultIndexer(Indexer, ABC):
    """If this Indexer is used, it is because we could not match the file to a more specific Indexer."""
    pass


indexer_map = defaultdict(lambda: DefaultIndexer)


def find_indexer(file) -> Type[Indexer]:
    """Find the Indexer for a given File model."""
    if not file.mimetype:
        return DefaultIndexer

    if file.mimetype in indexer_map:
        # Use the specific indexer.
        indexer = indexer_map[file.mimetype]
    else:
        # Use the broad indexer.
        indexer = indexer_map[file.mimetype.split('/')[0]]

    indexer = indexer.detect_special_indexer(file)

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


@register_indexer('application/gzip', 'application/x-bzip2', 'application/zip')
class ZipIndexer(Indexer, ABC):
    """Handles archive files lik zip/gzip/bzip."""

    @classmethod
    def create_index(cls, file):
        a = cls.get_title(file)
        file_names = cls.get_file_names(file)
        return a, None, None, file_names

    @classmethod
    def get_file_names(cls, file) -> List[str]:
        """Return all the names of the files in the zip file."""
        path = file.path.path if hasattr(file.path, 'path') else file.path
        try:
            with ZipFile(path, 'r') as zip_:
                file_names = [pathlib.Path(name).name for name in zip_.namelist()]
                return file_names
        except Exception as e:
            logger.error(f'Unable to get information from zip: {path}', exc_info=e)


WORD_SPLITTER = re.compile(r"([\w’'-]+)")
MAX_TEXT_FILE_BYTES = 100_000


@register_indexer('text/plain')
class TextIndexer(Indexer, ABC):
    """Handles plain text files.

    Detects VTT (caption) files and forwards them on."""

    @classmethod
    def create_index(cls, file):
        path = file.path.path if hasattr(file.path, 'path') else file.path
        a = cls.get_title(file)
        words = cls.get_words(path)
        return a, None, None, words

    @staticmethod
    def get_words(path: pathlib.Path) -> List[str]:
        """Read the words from a file."""
        # TODO this only supports English.
        contents = path.read_text()
        words = WORD_SPLITTER.findall(contents)
        return words

    @classmethod
    def detect_special_indexer(cls, file):
        if file.path.name.endswith('.json'):
            # JSON files are detected as "text/plain" but we don't want them to be indexed.
            return DefaultIndexer
        if file.path.name.endswith('.vtt') or file.path.name.endswith('.srt'):
            # Don't process caption files.
            return DefaultIndexer
        return cls
