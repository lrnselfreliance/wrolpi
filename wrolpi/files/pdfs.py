import asyncio
import dataclasses
import pathlib
from typing import Generator

import pytz

from wrolpi import dates
from wrolpi.common import register_modeler, logger, truncate_generator_bytes, truncate_object_bytes, \
    split_lines_by_length, slow_logger
from wrolpi.db import get_db_session
from wrolpi.files.indexers import Indexer
from wrolpi.files.models import FileGroup
from wrolpi.vars import FILE_MAX_PDF_SIZE, PYTEST, FILE_MAX_TEXT_SIZE

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

logger = logger.getChild(__name__)

__all__ = ['get_pdf_metadata', 'get_words', 'pdf_modeler']


@dataclasses.dataclass
class PDFMetadata:
    title: str = None
    author: str = None
    published_datetime: str = None
    modification_datetime: str = None


def get_pdf_metadata(reader: PdfReader, path: pathlib.Path) -> PDFMetadata:
    """Extract title/author from the PDF metadata."""
    data = PDFMetadata()

    if reader is None or reader.metadata is None:
        logger.error(f'Cannot get title of {path} PyPDF2 is not installed.')
        data.title = Indexer.get_title(path)
        return data

    if (title := reader.metadata.title) and title.lower() != 'unknown':
        data.title = title
    if (author := reader.metadata.author) and author.lower() != 'unknown':
        data.author = author

    if reader.metadata.creation_date_raw:
        try:
            str(reader.metadata.creation_date)
            data.published_datetime = reader.metadata.creation_date
        except ValueError:
            # pypdf could not parse the date, lets give it a try...
            data.published_datetime = dates.strpdate(reader.metadata.creation_date_raw)
        if not data.published_datetime.tzinfo:
            data.published_datetime = data.published_datetime.astimezone(pytz.UTC)

    if reader.metadata.modification_date_raw:
        try:
            str(reader.metadata.modification_date)
            data.modification_datetime = reader.metadata.modification_date
        except ValueError:
            # pypdf could not parse the date, lets give it a try...
            data.modification_datetime = dates.strpdate(reader.metadata.modification_date_raw)
        if not data.modification_datetime.tzinfo:
            data.modification_datetime = data.modification_datetime.astimezone(pytz.UTC)

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
                    file_title = Indexer.get_title(pdf_file)

                    reader = PdfReader(pdf_file)

                    with slow_logger(2, f'Modeling PDF took %(elapsed)s seconds: {file_group}',
                                     logger__=logger):
                        metadata = get_pdf_metadata(reader, pdf_file)

                        words = ''
                        if pdf_file.stat().st_size > FILE_MAX_PDF_SIZE:
                            logger.warning(f'PDF too large to fully index: {pdf_file}')
                        else:
                            try:
                                # PDFs are complex, don't fail to create title index if text extraction fails.
                                words = '\n'.join(
                                    truncate_generator_bytes(get_words(reader, pdf_file), FILE_MAX_TEXT_SIZE))
                                words = truncate_object_bytes(words, FILE_MAX_TEXT_SIZE)
                                words = split_lines_by_length(words)
                            except Exception as e:
                                logger.error(f'Failed to index {pdf_file}', exc_info=e)
                                if PYTEST:
                                    raise

                        file_group.title = file_group.a_text = metadata.title or file_title
                        file_group.author = file_group.b_text = metadata.author
                        file_group.c_text = file_title  # The name of the file may not match the title in the PDF metadata.
                        file_group.d_text = words or None
                        file_group.published_datetime = metadata.published_datetime
                        file_group.published_modified_datetime = metadata.modification_datetime
                        file_group.model = 'pdf'
                except Exception as e:
                    logger.error(f'Failed to index PDF {pdf_file}', exc_info=e)
                    if PYTEST:
                        raise

                # Even if indexing fails, we mark it as indexed.  We won't retry indexing this.
                file_group.indexed = True

                # Sleep to catch cancel.
                await asyncio.sleep(0)

            logger.info(f'pdf_modeler processed {processed} PDFs')

            session.commit()

            if processed < PDF_PROCESSING_LIMIT:
                # Did not reach limit, do not query again.
                break

        # Sleep to catch cancel.
        await asyncio.sleep(0)
