import pytest

from modules.docs.extractors import extract_epub, extract_pdf, extract_metadata, extract_docx, extract_odt, \
    extract_doc, extract_cbz, DocMetadata
from wrolpi.files.models import FileGroup


@pytest.mark.asyncio
async def test_extract_epub(test_session, test_directory, example_epub):
    """Metadata can be extracted from an EPUB file."""
    metadata = extract_epub(example_epub)
    assert metadata.title == 'WROLPi Test Book'
    assert metadata.author == 'roland'
    assert metadata.text  # Has text content.
    assert metadata.cover_bytes  # Has a cover image.


@pytest.mark.asyncio
async def test_extract_pdf(test_session, test_directory, example_pdf):
    """Metadata can be extracted from a PDF file."""
    metadata = extract_pdf(example_pdf)
    # PDF may or may not have title metadata; at minimum it should return something.
    assert metadata is not None
    assert isinstance(metadata, DocMetadata)


@pytest.mark.asyncio
async def test_extract_pdf_metadata(test_session, test_directory, example_pdf):
    """PDF extractor extracts page count, date, cover, and text."""
    metadata = extract_pdf(example_pdf)
    assert metadata.title == 'WROLPi Test PDF'
    assert metadata.author == 'roland'
    assert metadata.page_count == 3
    assert metadata.published_date is not None
    assert metadata.cover_bytes
    assert metadata.text


@pytest.mark.asyncio
async def test_extract_docx(test_session, test_directory, example_docx):
    """DOCX extractor extracts text content."""
    metadata = extract_docx(example_docx)
    assert isinstance(metadata, DocMetadata)
    assert metadata.title == 'Word Document'
    assert metadata.text
    assert 'Example Word Document' in metadata.text


@pytest.mark.asyncio
async def test_extract_odt(test_session, test_directory, example_odt):
    """ODT extractor extracts title and text."""
    metadata = extract_odt(example_odt)
    assert metadata.title is not None
    assert metadata.text
    assert 'Test Header' in metadata.text


@pytest.mark.asyncio
async def test_extract_doc(test_session, test_directory, example_doc):
    """DOC extractor extracts title from filename and text if catdoc/textutil available."""
    metadata = extract_doc(example_doc)
    assert metadata.title  # At minimum, title from filename.


@pytest.mark.asyncio
async def test_extract_cbz(test_session, test_directory, example_cbz):
    """CBZ extractor extracts cover image."""
    metadata = extract_cbz(example_cbz)
    assert metadata.cover_bytes is not None
    assert len(metadata.cover_bytes) > 0


@pytest.mark.asyncio
async def test_extract_cbz_comicinfo(test_session, test_directory, example_cbz_metadata):
    """CBZ extractor reads ComicInfo.xml metadata."""
    metadata = extract_cbz(example_cbz_metadata)
    assert metadata.title == 'Bobby Make-Believe #1'
    assert metadata.author == 'Frank King'
    assert metadata.publisher == 'Chicago Tribune'
    assert metadata.description == 'Bobby Make-Believe is a comic strip by Frank King.'
    assert metadata.language == 'en'
    assert metadata.subject == 'Comic Strip'
    assert metadata.page_count == 4
    assert metadata.published_date.year == 1915
    assert metadata.published_date.month == 6
    assert metadata.published_date.day == 15
    assert metadata.cover_bytes is not None


@pytest.mark.asyncio
async def test_extract_cbt(test_session, test_directory, example_cbt):
    """CBT (TAR) extractor extracts cover image."""
    metadata = extract_cbz(example_cbt)
    assert metadata.cover_bytes is not None
    assert len(metadata.cover_bytes) > 0


@pytest.mark.asyncio
async def test_extract_cbr(test_session, test_directory, example_cbr):
    """CBR (RAR) extractor extracts cover image."""
    metadata = extract_cbz(example_cbr)
    assert metadata.cover_bytes is not None
    assert len(metadata.cover_bytes) > 0


@pytest.mark.asyncio
async def test_extract_cb7(test_session, test_directory, example_cb7):
    """CB7 (7z) extractor extracts cover image."""
    metadata = extract_cbz(example_cb7)
    assert metadata.cover_bytes is not None
    assert len(metadata.cover_bytes) > 0


@pytest.mark.asyncio
async def test_extract_metadata_cbt(test_session, test_directory, example_cbt):
    """extract_metadata dispatches CBT files to the comic extractor."""
    fg = FileGroup.from_paths(test_session, example_cbt)
    test_session.flush()
    metadata = extract_metadata(fg)
    assert metadata.cover_bytes is not None
    assert len(metadata.cover_bytes) > 0


@pytest.mark.asyncio
async def test_extract_metadata_cb7(test_session, test_directory, example_cb7):
    """extract_metadata dispatches CB7 files to the comic extractor."""
    fg = FileGroup.from_paths(test_session, example_cb7)
    test_session.flush()
    metadata = extract_metadata(fg)
    assert metadata.cover_bytes is not None
    assert len(metadata.cover_bytes) > 0


@pytest.mark.asyncio
async def test_extract_metadata_dispatches(test_session, test_directory, example_epub):
    """extract_metadata dispatches to the correct extractor based on mimetype."""
    fg = FileGroup.from_paths(test_session, example_epub)
    test_session.flush()

    metadata = extract_metadata(fg)
    assert metadata.title == 'WROLPi Test Book'
    assert metadata.author == 'roland'
