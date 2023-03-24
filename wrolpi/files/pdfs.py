import asyncio
import dataclasses
import pathlib
from typing import Generator

from wrolpi.common import register_modeler, logger, truncate_generator_bytes, truncate_object_bytes, \
    split_lines_by_length
from wrolpi.db import get_db_session
from wrolpi.files.indexers import Indexer
from wrolpi.files.models import FileGroup
from wrolpi.vars import FILE_MAX_PDF_SIZE, PYTEST, FILE_MAX_TEXT_SIZE

try:
    from PyPDF2 import PdfReader
except ImportError:
    PdfReader = None

logger = logger.getChild(__name__)

__all__ = ['get_pdf_metadata', 'get_words', 'pdf_modeler']


@dataclasses.dataclass
class PDFMetadata:
    title: str = None
    author: str = None
    text: str = None


def create_index(path):
    file_title = Indexer.get_title(path)

    reader = PdfReader(path)

    data = get_pdf_metadata(reader, path)

    if path.stat().st_size > FILE_MAX_PDF_SIZE:
        logger.warning(f'PDF too large to fully index: {path}')
        return data.title, data.author, file_title, None

    words = ''
    try:
        # PDFs are complex, don't fail to create title index if text extraction fails.
        words = '\n'.join(truncate_generator_bytes(get_words(reader, path), FILE_MAX_TEXT_SIZE))
        words = truncate_object_bytes(words, FILE_MAX_TEXT_SIZE)
        words = split_lines_by_length(words)
    except Exception as e:
        logger.error(f'Failed to index {path}', exc_info=e)
        if PYTEST:
            raise
    return data.title, data.author, file_title, words


def get_pdf_metadata(reader: PdfReader, path: pathlib.Path) -> PDFMetadata:
    """Extract title/author from the PDF metadata."""
    data = PDFMetadata()

    if reader is None or reader.metadata is None:
        logger.error(f'Cannot get title of {path} PyPDF2 is not installed.')
        data.title = Indexer.get_title(path)
        return data

    data.title = reader.metadata.title
    data.author = reader.metadata.author
    return data


def get_words(reader: PdfReader, path: pathlib.Path) -> Generator[str, None, None]:
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


# PDFs can be large, limit how many are modeled at once.
PDF_PROCESSING_LIMIT = 10


@register_modeler
async def pdf_modeler():
    """Queries for any PDF files that have not been indexed.  Each PDF found will be indexed."""
    if not PdfReader:
        logger.warning(f'Cannot index PDF without PyPDF2')
        return

    while True:
        # Continually query for PDFs that have not been indexed.
        with get_db_session(commit=True) as session:
            file_groups = session.query(FileGroup) \
                .filter(
                # Get all groups that contain a PDF that have not been indexed.
                FileGroup.indexed != True,
                FileGroup.mimetype == 'application/pdf',
            ).limit(PDF_PROCESSING_LIMIT)

            processed = 0
            for file_group in file_groups:
                processed += 1
                pdf_files = file_group.my_files('application/pdf')
                if not pdf_files:
                    logger.error('Query returned a group without a PDF!')
                    continue

                # Assume the first PDF is the only PDF.
                pdf_file = pdf_files[0]['path']
                try:
                    title, author, file_title, contents = create_index(pdf_file)
                    file_group.data = {'author': author}
                    file_group.title = file_group.a_text = title
                    file_group.b_text = author
                    file_group.c_text = file_title
                    file_group.d_text = contents
                except Exception as e:
                    logger.error(f'Failed to index PDF {pdf_file}', exc_info=e)
                    if PYTEST:
                        raise

                # Even if indexing fails, we mark it as indexed.  We won't retry indexing this.
                file_group.indexed = True

            if processed:
                logger.debug(f'pdf_modeler processed {processed} PDFs')

            if processed < PDF_PROCESSING_LIMIT:
                # Did not reach limit, do not query again.
                break

        # Sleep to catch cancel.
        await asyncio.sleep(0)
