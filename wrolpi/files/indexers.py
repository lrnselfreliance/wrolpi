import dataclasses
import pathlib
import re
from abc import ABC
from collections import defaultdict
from typing import List, Type, Tuple, Generator
from zipfile import ZipFile

from wrolpi.vars import PYTEST, FILE_MAX_PDF_SIZE, FILE_MAX_TEXT_SIZE

try:
    from PyPDF2 import PdfReader
except ImportError:
    PdfReader = None

from wrolpi.common import logger, truncate_generator_bytes

logger = logger.getChild(__name__)

__all__ = ['Indexer', 'DefaultIndexer', 'ZipIndexer', 'TextIndexer', 'find_indexer', 'register_indexer']


class Indexer(object):

    @staticmethod
    def get_title(file):
        from wrolpi.files.lib import split_file_name_words
        path = file.path.path if hasattr(file.path, 'path') else file.path
        words = split_file_name_words(path.name)
        return words

    @classmethod
    def create_index(cls, file) -> Tuple:
        # All files can have their title as the highest priority search.
        a = cls.get_title(file)
        return a, None, None, None


class DefaultIndexer(Indexer, ABC):
    """If this Indexer is used, it is because we could not match the file to a more specific Indexer."""
    pass


indexer_map = defaultdict(lambda: DefaultIndexer)


def find_indexer(file) -> Type[Indexer]:
    """Find the Indexer for a given File model."""
    if not file.mimetype:
        return DefaultIndexer

    # Get the indexer that matches the mimetype of this file.
    indexer = next((v for k, v in indexer_map.items() if file.mimetype.startswith(k)), None)

    if not indexer:
        # Use the broad indexer.
        indexer = indexer_map[file.mimetype.split('/')[0]]

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
    def create_index(cls, file):
        a = cls.get_title(file)
        file_names = cls.get_file_names(file)
        return a, None, None, file_names

    @classmethod
    def get_file_names(cls, file) -> List[str]:
        """Return all the names of the files in the zip file."""
        path = file.path.path if hasattr(file.path, 'path') else file.path
        from wrolpi.files.lib import split_file_name_words
        try:
            with ZipFile(path, 'r') as zip_:
                file_names = [' '.join(split_file_name_words(pathlib.Path(name).name)) for name in zip_.namelist()]
                return file_names
        except Exception as e:
            logger.error(f'Unable to get information from zip: {path}', exc_info=e)
            if PYTEST:
                raise


WORD_SPLITTER = re.compile(r"([\w’'-]+)")


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


@dataclasses.dataclass
class PDFMetadata:
    title: str = None
    author: str = None


@register_indexer('application/pdf')
class PDFIndexer(Indexer, ABC):
    """Uses PyPDF2 to extract text from a PDF."""

    @classmethod
    def create_index(cls, file):
        path: pathlib.Path = file.path.path if hasattr(file.path, 'path') else file.path

        file_title = super().get_title(file)

        reader = None
        if PdfReader is not None:
            reader = PdfReader(path)

        data = cls.get_pdf_metadata(reader, file)

        if path.stat().st_size > FILE_MAX_PDF_SIZE:
            logger.warning(f'PDF too large to fully index: {path}')
            return data.title, data.author, file_title, None

        words = ''
        try:
            # PDFs are complex, don't fail to create title index if text extraction fails.
            words = '\n'.join(truncate_generator_bytes(cls.get_words(reader, path), FILE_MAX_TEXT_SIZE))
        except Exception as e:
            logger.error(f'Failed to index {path}', exc_info=e)
            if PYTEST:
                raise
        return data.title, data.author, file_title, words

    @classmethod
    def get_pdf_metadata(cls, reader: PdfReader, file) -> PDFMetadata:
        """Extract title/author from the PDF metadata."""
        path = file.path.path if hasattr(file.path, 'path') else file.path

        data = PDFMetadata()

        if reader is None:
            logger.error(f'Cannot get title of {path} PyPDF2 is not installed.')
            data.title = super().get_title(file)
            return data

        data.title = reader.metadata.title
        data.author = reader.metadata.author
        return data

    @classmethod
    def get_words(cls, reader: PdfReader, path: pathlib.Path) -> Generator[str, None, None]:
        """
        Reads all text facing up in a PDF.

        Note, may return more than can be stored in Postgres.  See: truncate_generator_bytes
        """
        if PdfReader is None:
            logger.error(f'Cannot index {path} PyPDF2 is not installed.')
            yield ''
            return

        for page in reader.pages:
            # Get all text facing up.
            text = page.extract_text(0)
            # Postgres does not allow null characters.
            text = text.replace('\x00', '\uFFFD').strip()
            if text:
                yield text
