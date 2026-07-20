import asyncio
import logging
from typing import Callable, List

from sqlalchemy import or_
from sqlalchemy.exc import OperationalError
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
from .models import Doc, DocSection, DOC_MIMETYPES, COMIC_BOOK_SUFFIXES, EPUB_MIMETYPE, MOBI_MIMETYPE

logger = logging.getLogger(__name__)

DOC_PROCESSING_LIMIT = 10
# Retries for a single doc when it hits SQLite's "database is locked" (SQLITE_BUSY_SNAPSHOT).
DOC_LOCK_RETRIES = 3


@register_modeler
async def doc_modeler(progress_callback: Callable[[int], None] = None):
    """Searches for doc files (epub, mobi, pdf, docx, doc, odt, cbz, cbr) and models them.

    Each doc is modeled in its own short transaction.  Modeling reads a large file (a PDF/epub can
    be tens of MB) and can take seconds; holding one write transaction across a whole batch let
    another connection commit in the meantime, so the deferred transaction failed to upgrade to a
    write with SQLite's `SQLITE_BUSY_SNAPSHOT` ("database is locked", which `busy_timeout` does not
    absorb) -- and the error handler then crashed on the rolled-back session, aborting the entire
    modeler run.  Per-doc transactions keep the write window short and isolate failures so one
    locked/broken doc cannot poison the rest of the run.
    """
    total_processed = 0
    # Ids of docs that failed to model this run.  A failed doc keeps matching the `Doc.id IS NULL`
    # gate below, so without excluding it the loop would re-select it forever, hang, and starve
    # later docs.  Successfully-modeled docs are excluded automatically (they gain a Doc row), so
    # only failures need tracking -- keeping this set (and the `notin_` clause) small.  Failed docs
    # are retried on the next refresh.
    failed_ids: set = set()
    while True:
        # Short read-only transaction to choose the next batch of ids.  Do NOT hold it open across
        # the slow per-doc modeling below.
        with get_db_session() as session:
            query = session.query(FileGroup.id) \
                .outerjoin(Doc, Doc.file_group_id == FileGroup.id) \
                .filter(
                or_(
                    *[FileGroup.mimetype == mt for mt in DOC_MIMETYPES],
                    *[FileGroup.primary_path.like(f'%{suffix}') for suffix in COMIC_BOOK_SUFFIXES],
                ),
                # Model any doc that has no Doc row yet (even if `apply_indexers` already set
                # `indexed=True` before this modeler ran), or any doc explicitly flagged for
                # re-indexing.  Gating solely on `indexed == False` left already-indexed docs
                # permanently unmodeled and invisible in /api/docs.
                or_(
                    Doc.id.is_(None),
                    FileGroup.indexed == False,
                ),
            )
            if failed_ids:
                query = query.filter(FileGroup.id.notin_(failed_ids))
            fg_ids: List[int] = [row[0] for row in query.limit(DOC_PROCESSING_LIMIT).all()]

        if not fg_ids:
            break

        for fg_id in fg_ids:
            for attempt in range(DOC_LOCK_RETRIES):
                try:
                    # One short write transaction per doc.
                    with get_db_session(commit=True) as session:
                        file_group = session.query(FileGroup).get(fg_id)
                        if file_group is None:
                            # Deleted between discovery and now; nothing to model.
                            break
                        doc = _model_doc(file_group, session)
                        session.add(doc)
                        file_group.model = Doc.__tablename__
                        file_group.indexed = True
                    break
                except OperationalError as e:
                    # Another connection committed during our transaction.  Retrying with a fresh
                    # transaction gets a fresh snapshot and usually succeeds.
                    if 'locked' in str(e).lower() and attempt < DOC_LOCK_RETRIES - 1:
                        await asyncio.sleep(0.2 * (attempt + 1))
                        continue
                    logger.error(f'Failed to model doc file_group_id={fg_id}: database error', exc_info=e)
                    failed_ids.add(fg_id)
                    break
                except Exception as e:
                    # Never reference the ORM object here: after a failed flush the session is
                    # rolled back, so touching a lazy/expired attribute (e.g. in its repr) raises a
                    # second exception that would abort the whole modeler.  Log the plain id only.
                    logger.error(f'Failed to model doc file_group_id={fg_id}', exc_info=e)
                    failed_ids.add(fg_id)
                    if PYTEST:
                        raise
                    break
            # Yield so a cancel/other tasks can run between docs.
            await asyncio.sleep(0)

        total_processed += len(fg_ids)
        if progress_callback:
            progress_callback(total_processed)


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

    # Ensure the Doc has an id before inserting DocSection rows that reference it.
    doc.flush()

    # Replace any existing sections with the freshly-extracted ones.
    _replace_doc_sections(session, doc, metadata.sections)

    return doc


def _replace_doc_sections(session: Session, doc: Doc, sections):
    """Delete any DocSection rows for this Doc and insert the new ones.

    Using a bulk delete + bulk insert keeps this O(N) without SQLAlchemy tracking
    each old row. Callers must have flushed `doc` so it has an id.
    """
    session.query(DocSection).filter(DocSection.doc_id == doc.id).delete(synchronize_session=False)
    if not sections:
        return
    session.bulk_save_objects([
        DocSection(
            doc_id=doc.id,
            kind=s.kind,
            ordinal=s.ordinal,
            label=s.label,
            content=s.content,
        ) for s in sections
    ])


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
