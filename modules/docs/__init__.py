import asyncio
import logging
from typing import Callable, List, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session

from wrolpi.common import register_modeler, register_refresh_cleanup, \
    truncate_object_bytes, split_lines_by_length
from wrolpi.db import get_db_session
from wrolpi.files.indexers import Indexer
from wrolpi.files.models import FileGroup
from wrolpi.vars import PYTEST, FILE_MAX_TEXT_SIZE
from .extractors import extract_metadata
from .lib import get_or_create_subject_collection, get_or_create_author_collection, is_valid_author, split_authors, \
    normalize_author, normalize_subject, split_subjects, is_valid_subject, discover_calibre_cover
from .models import Doc, DOC_MIMETYPES, COMIC_BOOK_SUFFIXES, EPUB_MIMETYPE, MOBI_MIMETYPE

logger = logging.getLogger(__name__)

DOC_PROCESSING_LIMIT = 10


@register_modeler
async def doc_modeler(progress_callback: Callable[[int], None] = None):
    """Searches for doc files (epub, mobi, pdf, docx, doc, odt, cbz, cbr) and models them."""
    total_processed = 0
    while True:
        with get_db_session(commit=True) as session:
            file_groups = session.query(FileGroup, Doc).filter(
                or_(
                    *[FileGroup.mimetype == mt for mt in DOC_MIMETYPES],
                    *[FileGroup.primary_path.like(f'%{suffix}') for suffix in COMIC_BOOK_SUFFIXES],
                ),
                FileGroup.indexed == False,
            ).outerjoin(Doc, Doc.file_group_id == FileGroup.id) \
                .limit(DOC_PROCESSING_LIMIT)
            file_groups: List[Tuple[FileGroup, Doc]] = list(file_groups)

            processed = 0
            for file_group, doc in file_groups:
                processed += 1
                try:
                    if PYTEST:
                        session.expire(file_group)

                    doc = _model_doc(file_group, session)
                    session.add(doc)
                    file_group.model = Doc.__tablename__
                    file_group.indexed = True
                except Exception as e:
                    logger.error(f'Failed to index doc {file_group}', exc_info=e)
                    file_group.indexed = True  # Don't retry on failure.
                    if PYTEST:
                        raise

            session.commit()

            total_processed += len(file_groups)
            if progress_callback and len(file_groups) > 0:
                progress_callback(total_processed)

            if processed < DOC_PROCESSING_LIMIT:
                break

        await asyncio.sleep(0)


def _model_doc(file_group: FileGroup, session: Session) -> Doc:
    """Creates a Doc model from a FileGroup. Extracts metadata and creates collections."""
    doc = session.query(Doc).filter_by(file_group_id=file_group.id).one_or_none()
    if not doc:
        doc = Doc(file_group=file_group)
        session.add(doc)

    metadata = extract_metadata(file_group)

    if metadata.title:
        file_group.title = file_group.a_text = metadata.title
    if metadata.author:
        file_group.author = file_group.b_text = metadata.author
    if metadata.text:
        text = truncate_object_bytes(metadata.text, FILE_MAX_TEXT_SIZE)
        text = split_lines_by_length(text)
        file_group.d_text = text

    # Set c_text to filename for search.
    file_title = Indexer.get_title(file_group.primary_path)
    file_group.c_text = file_title

    if not file_group.title:
        file_group.title = file_title

    if metadata.published_date:
        file_group.published_datetime = metadata.published_date

    # Update Doc-specific fields.
    doc.publisher = metadata.publisher
    doc.language = metadata.language
    doc.page_count = metadata.page_count
    doc.subject = metadata.subject
    doc.description = metadata.description
    doc.size = file_group.primary_path.stat().st_size if file_group.primary_path.exists() else None

    # Handle cover.
    _handle_doc_cover(doc, file_group, metadata)

    # Store data dict.
    data = file_group.data or {}
    if metadata.title:
        data['title'] = metadata.title
    if metadata.author:
        data['author'] = metadata.author
    # Store primary doc path as relative filename.
    data['doc_path'] = file_group.primary_path.name
    file_group.data = data

    # Auto-create collections.
    _auto_create_collections(session, file_group, metadata)

    doc.flush()
    return doc


def _handle_doc_cover(doc: Doc, file_group: FileGroup, metadata):
    """Handle cover extraction and storage for a doc."""

    # Check for Calibre cover first (epub only) — must happen before poster check
    # since Calibre cover has a different stem ("cover.jpg" not matching epub stem).
    if file_group.mimetype and file_group.mimetype.startswith('application/epub'):
        if calibre_cover := discover_calibre_cover(file_group.primary_path):
            doc._hide_calibre_files(file_group)
            file_group.append_files(calibre_cover)
            file_group.data = file_group.data or {}
            file_group.data['cover_path'] = calibre_cover.name
            return

    # Use existing poster files if present.
    poster_files = file_group.my_poster_files()
    if poster_files:
        file_group.data = file_group.data or {}
        file_group.data['cover_path'] = poster_files[0]['path'].name
        return

    # Use cover from metadata extraction (epub internal cover, PDF first page, etc.)
    cover_bytes = metadata.cover_bytes
    if cover_bytes:
        cover_path = file_group.primary_path.with_suffix('.jpeg')
        cover_path.write_bytes(cover_bytes)
        file_group.append_files(cover_path)
        file_group.data = file_group.data or {}
        file_group.data['cover_path'] = cover_path.name


def _auto_create_collections(session: Session, file_group: FileGroup, metadata):
    """Auto-create author/subject collections and link the file_group."""
    if metadata.author:
        for author in split_authors(metadata.author):
            author = normalize_author(author)
            if author and is_valid_author(author):
                col = get_or_create_author_collection(session, author)
                if col:
                    col.add_file_group(file_group, session=session)

    if metadata.subject:
        for subject in split_subjects(metadata.subject):
            subject = normalize_subject(subject)
            if subject and is_valid_subject(subject):
                col = get_or_create_subject_collection(session, subject)
                if col:
                    col.add_file_group(file_group, session=session)


@register_refresh_cleanup
def doc_cleanup(test_directory=None):
    """Remove empty author/subject collections after refresh."""
    from sqlalchemy import func
    from wrolpi.collections.models import Collection, CollectionItem

    with get_db_session(commit=True) as session:
        empty_collections = session.query(Collection).filter(
            Collection.kind.in_(['author', 'subject']),
        ).outerjoin(CollectionItem).group_by(Collection.id).having(
            func.count(CollectionItem.id) == 0,
        ).all()
        for collection in empty_collections:
            logger.info(f'Removing empty {collection.kind} collection: {collection.name}')
            session.delete(collection)
