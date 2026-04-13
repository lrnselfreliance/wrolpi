"""Tests for the doc_modeler."""
import shutil
from unittest.mock import patch

import pytest
from PIL import Image

from modules.docs import doc_modeler
from modules.docs.models import Doc, DocSection
from wrolpi.dates import now
from wrolpi.files import lib as files_lib
from wrolpi.files.models import FileGroup
from wrolpi.files.worker import file_worker
from wrolpi.test.common import assert_dict_contains
from wrolpi.vars import PROJECT_DIR


@pytest.mark.asyncio
async def test_doc_modeler_epub(async_client, test_session, test_directory, example_epub, example_mobi, refresh_files):
    """Doc modeler indexes epub files."""
    await refresh_files()

    doc: Doc = test_session.query(Doc).one()
    assert doc.file_group.title == 'WROLPi Test Book'
    assert doc.file_group.mimetype.startswith('application/epub')
    assert doc.file_group.author == 'roland'
    assert doc.file_group.a_text, 'Book title was not indexed'
    assert doc.file_group.b_text, 'Book author was not indexed'
    assert doc.file_group.d_text, 'Book text was not indexed'
    assert doc.file_group.model == 'doc'

    # Both ebooks are assumed to be the same book.
    assert (epubs := doc.file_group.my_files('application/epub+zip')) and len(epubs) == 1
    assert (mobis := doc.file_group.my_files('application/x-mobipocket-ebook')) and len(mobis) == 1
    # Cover was discovered.
    assert len(doc.file_group.my_poster_files()) == 1

    # A second refresh should not re-model the already-indexed doc.
    with patch('modules.docs._model_doc', side_effect=AssertionError('_model_doc should not be called')):
        await refresh_files()


@pytest.mark.asyncio
async def test_doc_modeler_pdf(async_client, test_session, test_directory, example_pdf, refresh_files):
    """Doc modeler indexes PDF files."""
    await refresh_files()

    doc: Doc = test_session.query(Doc).one()
    assert doc.file_group.mimetype == 'application/pdf'
    assert doc.file_group.model == 'doc'
    assert doc.file_group.indexed is True
    assert doc.size  # Has a size.


@pytest.mark.asyncio
async def test_doc_modeler_persists_epub_sections(async_client, test_session, test_directory,
                                                  example_epub, refresh_files):
    """After modeling, per-spine-item DocSection rows exist for an EPUB."""
    await refresh_files()

    doc: Doc = test_session.query(Doc).one()
    sections = test_session.query(DocSection).filter_by(doc_id=doc.id) \
        .order_by(DocSection.ordinal).all()
    assert sections, 'EPUB modeler should produce DocSection rows'
    assert all(s.kind == 'epub_spine' for s in sections)
    assert [s.ordinal for s in sections] == list(range(len(sections)))


@pytest.mark.asyncio
async def test_doc_modeler_persists_pdf_sections(async_client, test_session, test_directory,
                                                 example_pdf, refresh_files):
    """After modeling, per-page DocSection rows exist for a PDF."""
    await refresh_files()

    doc: Doc = test_session.query(Doc).one()
    sections = test_session.query(DocSection).filter_by(doc_id=doc.id) \
        .order_by(DocSection.ordinal).all()
    assert sections, 'PDF modeler should produce DocSection rows'
    assert all(s.kind == 'pdf_page' for s in sections)
    # 1-based ordinals, test PDF has 3 pages.
    assert [s.ordinal for s in sections] == [1, 2, 3]


@pytest.mark.asyncio
async def test_doc_modeler_replaces_sections(async_client, test_session, test_directory,
                                             example_epub, refresh_files):
    """Re-modeling a Doc replaces its DocSection rows (no duplicates)."""
    from modules.docs import _model_doc

    await refresh_files()
    doc: Doc = test_session.query(Doc).one()
    initial_count = test_session.query(DocSection).filter_by(doc_id=doc.id).count()
    assert initial_count > 0

    # Re-run modeling on the same file_group and confirm we don't accumulate rows.
    _model_doc(doc.file_group, test_session)
    test_session.commit()
    final_count = test_session.query(DocSection).filter_by(doc_id=doc.id).count()
    assert final_count == initial_count


@pytest.mark.asyncio
async def test_doc_do_model_sets_model(test_session, example_pdf):
    """Doc.do_model sets file_group.model so the FileGroup is recognized as a doc."""
    files_lib._upsert_files([example_pdf], now())
    file_group = test_session.query(FileGroup).one()
    # Reset to simulate a newly discovered file.
    file_group.model = None
    file_group.indexed = False
    test_session.commit()

    file_group.do_model(test_session)
    test_session.commit()

    assert file_group.model == 'doc', 'do_model must set file_group.model'
    assert file_group.indexed is True


@pytest.mark.asyncio
async def test_doc_modeler_processes_more_than_batch_limit(async_client, test_session, test_directory):
    """Doc modeler processes more than one batch of files (limit=10)."""
    ebook_dir = test_directory / 'ebooks'
    ebook_dir.mkdir(parents=True)

    num_docs = 15
    for i in range(num_docs):
        path = ebook_dir / f'test_ebook_{i:03d}.epub'
        shutil.copy(PROJECT_DIR / 'test/ebook example.epub', path)

    # Create FileGroups.
    for path in ebook_dir.iterdir():
        fg = FileGroup.from_paths(test_session, path)
        assert fg.mimetype.startswith('application/epub')
    test_session.commit()

    await doc_modeler()

    doc_count = test_session.query(Doc).count()
    assert doc_count == num_docs, \
        f'doc_modeler should process ALL {num_docs} files, but only processed {doc_count}'

    still_unindexed = test_session.query(FileGroup).filter(
        FileGroup.indexed == False,
        FileGroup.mimetype == 'application/epub+zip',
    ).count()
    assert still_unindexed == 0


@pytest.mark.asyncio
async def test_doc_modeler_reindex_creates_collections(async_client, test_session, test_directory, example_epub,
                                                       refresh_files):
    """When a doc is re-indexed (indexed=false), author/subject collections should be re-created."""
    from wrolpi.collections.models import Collection

    from wrolpi.db import get_db_session

    await refresh_files()

    # Author collection was created during first modeling.
    with get_db_session() as session:
        doc = session.query(Doc).one()
        assert doc.file_group.author == 'roland'
        author_col = session.query(Collection).filter_by(kind='author', name='Roland').one_or_none()
        assert author_col, 'Author collection should exist after first indexing'

    # Simulate post-migration state: delete the collection and mark as unindexed.
    with get_db_session(commit=True) as session:
        author_col = session.query(Collection).filter_by(kind='author', name='Roland').one()
        session.delete(author_col)
        doc = session.query(Doc).one()
        doc.file_group.indexed = False

    # Verify collection is gone.
    with get_db_session() as session:
        assert session.query(Collection).filter_by(kind='author', name='Roland').one_or_none() is None

    # Re-run the modeler.
    await doc_modeler()

    # Author collection should be re-created.
    with get_db_session() as session:
        author_col = session.query(Collection).filter_by(kind='author', name='Roland').one_or_none()
        assert author_col, 'Author collection should be re-created when doc is re-indexed'


@pytest.mark.asyncio
async def test_doc_modeler_calibre_cover(test_session, async_client, test_directory, example_epub, example_mobi,
                                         image_file, refresh_files):
    """Calibre cover near an ebook file is discovered."""
    metadata = test_directory / 'metadata.opf'
    metadata.touch()
    cover_image = test_directory / 'cover.jpg'
    shutil.move(image_file, cover_image)

    await refresh_files()
    doc: Doc = test_session.query(Doc).one()
    assert doc.file_group.title == 'WROLPi Test Book'
    assert doc.cover_path
    assert {i['path'].name for i in doc.file_group.my_files()} == {'ebook example.epub', 'ebook example.mobi',
                                                                   'cover.jpg'}
    # Metadata and cover FileGroups were deleted.
    assert test_session.query(FileGroup).count() == 1


@pytest.mark.asyncio
async def test_doc_modeler_normalizes_author(async_client, test_session, test_directory, example_epub, refresh_files):
    """Author names are normalized before creating collections (e.g. quotes stripped)."""
    from wrolpi.collections.models import Collection
    from wrolpi.db import get_db_session

    # Patch extract_metadata to return a quoted author.
    from modules.docs.extractors import DocMetadata
    fake_metadata = DocMetadata(author='"Tony R. Kuphaldt"', title='Test Book')
    with patch('modules.docs.extract_metadata', return_value=fake_metadata):
        await refresh_files()

    with get_db_session() as session:
        # Collection should have normalized name (no quotes).
        col = session.query(Collection).filter_by(kind='author', name='Tony R. Kuphaldt').one_or_none()
        assert col, 'Author collection should have normalized name without quotes'
        # No collection with the quoted name.
        quoted = session.query(Collection).filter_by(kind='author', name='"Tony R. Kuphaldt"').one_or_none()
        assert not quoted, 'Should not create collection with quoted author name'


@pytest.mark.asyncio
async def test_doc_modeler_validates_subject(async_client, test_session, test_directory, example_epub, refresh_files):
    """Junk subjects are rejected during modeling."""
    from wrolpi.collections.models import Collection
    from wrolpi.db import get_db_session

    from modules.docs.extractors import DocMetadata
    fake_metadata = DocMetadata(subject='01/2004', title='Test Book')
    with patch('modules.docs.extract_metadata', return_value=fake_metadata):
        await refresh_files()

    with get_db_session() as session:
        col = session.query(Collection).filter_by(kind='subject', name='01/2004').one_or_none()
        assert not col, 'Should not create collection for date-like subject'


@pytest.mark.asyncio
async def test_doc_modeler_discover_local_cover(test_session, test_directory, example_epub, image_bytes_factory,
                                                refresh_files):
    """A cover file near the eBook is discovered."""
    cover_path = example_epub.with_suffix('.jpg')
    cover_path.write_bytes(image_bytes_factory())
    await refresh_files()

    doc: Doc = test_session.query(Doc).one()
    assert doc.cover_path.read_bytes() == cover_path.read_bytes()


@pytest.mark.asyncio
async def test_doc_modeler_extract_cover(test_session, test_directory, example_epub, refresh_files):
    """First image is extracted from the Ebook and used as the cover."""
    await refresh_files()

    doc: Doc = test_session.query(Doc).one()
    # The WROLPi logo is the first image in the example epub.
    assert doc.cover_path and doc.cover_path.stat().st_size == 297099


@pytest.mark.asyncio
async def test_doc_modeler_move_ebook(async_client, test_session, test_directory, example_epub, image_file, tag_factory,
                                      refresh_files, await_background_tasks):
    """An ebook is re-indexed when moved."""
    tag = await tag_factory()
    shutil.move(image_file, example_epub.with_suffix('.jpg'))
    await refresh_files()

    doc: Doc = test_session.query(Doc).one()
    assert doc.cover_path
    assert_dict_contains(doc.file_group.data, dict(author='roland'))
    assert sorted([i['path'] for i in doc.file_group.my_files()]) == [
        test_directory / 'ebook example.epub',
        test_directory / 'ebook example.jpg',
    ]
    doc.file_group.add_tag(test_session, tag.id)
    test_session.commit()

    new_directory = test_directory / 'new'
    new_directory.mkdir()
    file_worker.queue_move(new_directory, [doc.file_group.primary_path])
    await await_background_tasks()
    test_session.expire_all()

    doc: Doc = test_session.query(Doc).one()
    assert doc.file_group.primary_path == test_directory / 'new/ebook example.epub'
    assert doc.cover_path
    assert_dict_contains(doc.file_group.data, dict(author='roland'))
    assert sorted([i['path'] for i in doc.file_group.my_files()]) == [
        test_directory / 'new/ebook example.epub',
        test_directory / 'new/ebook example.jpg',
    ]


@pytest.mark.asyncio
async def test_doc_modeler_pdf_max_size(test_session, example_pdf):
    """The contents of a large PDF are not indexed."""
    example_pdf.write_bytes(example_pdf.read_bytes() * 5000)

    files_lib._upsert_files([example_pdf], now())

    await doc_modeler()
    file_group = test_session.query(FileGroup).one()
    assert file_group.d_text is None


@pytest.mark.asyncio
async def test_doc_modeler_pdf_poster(test_session, example_pdf):
    """PDF modeler finds an image with the same stem and uses it as the poster."""
    poster_path = example_pdf.with_suffix('.jpg')
    Image.new('RGB', (25, 25), color='grey').save(poster_path)

    files_lib._upsert_files([example_pdf, poster_path], now())

    await doc_modeler()
    file_group = test_session.query(FileGroup).one()
    assert file_group.indexed is True
    assert file_group.data is not None
    assert file_group.data.get('cover_path') == poster_path.name


