import asyncio
import dataclasses
import pathlib
from typing import Callable, Generator

import pytz

from wrolpi import dates
from wrolpi.common import register_modeler, logger, truncate_generator_bytes, truncate_object_bytes, \
    split_lines_by_length, slow_logger
from wrolpi.db import get_db_session
from wrolpi.files.indexers import Indexer
from wrolpi.files.models import FileGroup
from wrolpi.vars import FILE_MAX_PDF_SIZE, PYTEST, FILE_MAX_TEXT_SIZE

try:
    import pymupdf
except ImportError:
    pymupdf = None

logger = logger.getChild(__name__)

__all__ = ['get_pdf_metadata', 'get_words', 'pdf_modeler']


@dataclasses.dataclass
class PDFMetadata:
    title: str = None
    author: str = None
    published_datetime: str = None
    modification_datetime: str = None


def _parse_pdf_date(date_str: str):
    """Parse PDF date format 'D:YYYYMMDDHHmmSS+HH'mm'' to datetime."""
    if not date_str:
        return None
    try:
        parsed = dates.strpdate(date_str)
        if parsed and not parsed.tzinfo:
            parsed = parsed.astimezone(pytz.UTC)
        return parsed
    except Exception:
        return None


def get_pdf_metadata(doc, path: pathlib.Path) -> PDFMetadata:
    """Extract title/author from the PDF metadata."""
    data = PDFMetadata()

    if doc is None or doc.metadata is None:
        logger.error(f'Cannot get title of {path} PyMuPDF is not installed.')
        data.title = Indexer.get_title(path)
        return data

    metadata = doc.metadata

    if (title := metadata.get('title')) and title.lower() != 'unknown':
        data.title = title
    if (author := metadata.get('author')) and author.lower() != 'unknown':
        data.author = author

    if creation_date := metadata.get('creationDate'):
        data.published_datetime = _parse_pdf_date(creation_date)

    if mod_date := metadata.get('modDate'):
        data.modification_datetime = _parse_pdf_date(mod_date)

    return data


def get_words(doc, path: pathlib.Path) -> Generator[str, None, None]:
    """
    Reads all text in a PDF.

    Note, may return more than can be stored in Postgres.  See: truncate_generator_bytes
    """
    if pymupdf is None:
        logger.error(f'Cannot index {path} PyMuPDF is not installed.')
        yield ''
        return

    for page in doc:
        text = page.get_text()
        # Postgres does not allow null characters.
        text = text.replace('\x00', '\uFFFD').strip()
        if text:
            yield text


# PDFs can be large, limit how many are modeled at once.
PDF_PROCESSING_LIMIT = 10


@register_modeler
async def pdf_modeler(progress_callback: Callable[[int], None] = None):
    """Queries for any PDF files that have not been indexed.  Each PDF found will be indexed."""
    if not pymupdf:
        logger.warning(f'Cannot index PDF without PyMuPDF')
        return

    total_processed = 0
    while True:
        # Continually query for PDFs that have not been indexed.
        with get_db_session(commit=True) as session:
            file_groups = session.query(FileGroup) \
                .filter(
                # Get all groups that contain a PDF that have not been indexed.
                FileGroup.indexed != True,
                FileGroup.mimetype == 'application/pdf',
            ).limit(PDF_PROCESSING_LIMIT)
            file_groups = list(file_groups)

            processed = 0
            for file_group in file_groups:
                processed += 1
                pdf_files = file_group.my_files('application/pdf')
                if not pdf_files:
                    logger.error('Query returned a group without a PDF!')
                    continue

                # Assume the first PDF is the only PDF.
                pdf_file = pdf_files[0]['path']
                doc = None
                try:
                    file_title = Indexer.get_title(pdf_file)

                    doc = pymupdf.open(pdf_file)

                    with slow_logger(2, f'Modeling PDF took %(elapsed)s seconds: {file_group}',
                                     logger__=logger):
                        metadata = get_pdf_metadata(doc, pdf_file)

                        words = ''
                        if pdf_file.stat().st_size > FILE_MAX_PDF_SIZE:
                            logger.warning(f'PDF too large to fully index: {pdf_file}')
                        else:
                            try:
                                # PDFs are complex, don't fail to create title index if text extraction fails.
                                words = '\n'.join(
                                    truncate_generator_bytes(get_words(doc, pdf_file), FILE_MAX_TEXT_SIZE))
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

                        # Find an image with the same stem to use as the poster.
                        # Store as filename only (consistent with other models, enables fast moves/renames).
                        poster_files = file_group.my_poster_files()
                        if poster_files:
                            file_group.data = file_group.data or {}
                            file_group.data['poster_path'] = poster_files[0]['path'].name
                except Exception as e:
                    logger.error(f'Failed to index PDF {pdf_file}', exc_info=e)
                    if PYTEST:
                        raise
                finally:
                    if doc:
                        doc.close()

                # Even if indexing fails, we mark it as indexed.  We won't retry indexing this.
                file_group.indexed = True

                # Sleep to catch cancel.
                await asyncio.sleep(0)

            logger.info(f'pdf_modeler processed {processed} PDFs')

            session.commit()

            # Report batch progress
            total_processed += len(file_groups)
            if progress_callback and len(file_groups) > 0:
                progress_callback(total_processed)

            if processed < PDF_PROCESSING_LIMIT:
                # Did not reach limit, do not query again.
                break

        # Sleep to catch cancel.
        await asyncio.sleep(0)
